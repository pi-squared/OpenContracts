"""Parse through the verified patched Warp distribution in an isolated process."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from importlib import metadata, util
from pathlib import Path

from databricks_port.parser_exports import warp_export

VERSION = "2.1.0+oc39.1"


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


@dataclass(frozen=True)
class WarpParse:
    export: dict
    provenance: dict


def parse_warp_pdf(
    source,
    *,
    title,
    description="",
    apply_ocr=False,
    disable_ocr=False,
    semantic_units=True,
    include_images=False,
):
    """Return original word geometry and traceable source/parser/parse identities."""
    options = {
        "render_format": "opencontracts",
        "apply_ocr": apply_ocr,
        "disable_ocr": disable_ocr,
        "semantic_units": semantic_units,
        "include_images": include_images,
    }
    if any(
        type(options[name]) is not bool
        for name in ("apply_ocr", "disable_ocr", "semantic_units", "include_images")
    ):
        raise ValueError("Warp options must be booleans")
    if apply_ocr and disable_ocr:
        raise ValueError("Warp apply_ocr and disable_ocr are mutually exclusive")
    runtime = Path(
        os.environ.get("WARP_RUNTIME_ROOT", Path(__file__).parent / "warp_assets")
    )
    try:
        _verify_runtime(runtime)
    except (OSError, metadata.PackageNotFoundError, KeyError, TypeError) as error:
        raise ValueError(
            "The maintained Warp runtime is missing or incomplete"
        ) from error
    environment = {
        **os.environ,
        "WARP_RUNTIME_ROOT": str(runtime.resolve()),
        "WARP_FE_WORKERS": "1",
        "WARP_OCR_THREADS": "4",
        "OMP_NUM_THREADS": "4",
        "OPENBLAS_NUM_THREADS": "4",
        "PYTHONPATH": str(Path(__file__).resolve().parent.parent),
    }
    with tempfile.TemporaryDirectory(prefix="opencontracts-warp-") as temporary:
        directory = Path(temporary)
        input_path, output_path = directory / "source.pdf", directory / "export.json"
        input_path.write_bytes(source)
        try:
            result = subprocess.run(
                [
                    os.path.abspath(sys.executable),
                    "-m",
                    "databricks_port.warp_pdf",
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                    "--options",
                    json.dumps(options),
                ],
                cwd=directory,
                env=environment,
                capture_output=True,
                timeout=600,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise ValueError(
                "Verified Warp parser exceeded its 600-second limit"
            ) from error
        if result.returncode:
            # Warp's diagnostic streams can contain source text. Never copy
            # those streams into an exception, app response or public receipt.
            raise ValueError(f"Verified Warp parser failed (exit {result.returncode})")
        value = json.loads(output_path.read_text())
    value["export"].update(title=title, description=description)
    provenance = value["provenance"]
    provenance["export_sha256"] = hashlib.sha256(canonical(value["export"])).hexdigest()
    provenance["parsing_artifact_sha256"] = hashlib.sha256(
        canonical(provenance)
    ).hexdigest()
    return WarpParse(value["export"], provenance)


def _verify_runtime(runtime):
    """Reject changed installed bytes before importing Warp or OCR models."""
    receipt = json.loads((runtime / "warp-runtime.json").read_text())
    distribution = metadata.distribution("warp-ingest")
    if distribution.version != VERSION or receipt["version"] != VERSION:
        raise ValueError("The selected patched Warp distribution is not installed")
    package_root = Path(distribution.locate_file("warp_ingest")).resolve()
    spec = util.find_spec("warp_ingest")
    if spec is None or Path(spec.origin).resolve().parent != package_root:
        raise ValueError("Warp import resolves outside the verified distribution")
    actual_sources = {
        "warp_ingest/"
        + str(path.relative_to(package_root)): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in package_root.rglob("*.py")
    }
    if actual_sources != receipt["source_files"]:
        raise ValueError("Installed Warp source differs from the staged patched wheel")
    ocr = receipt["rapidocr"]
    ocr_distribution = metadata.distribution("rapidocr-onnxruntime")
    if ocr_distribution.version != ocr["version"]:
        raise ValueError("The selected headless RapidOCR distribution is not installed")
    ocr_root = Path(ocr_distribution.locate_file("rapidocr_onnxruntime")).resolve()
    ocr_spec = util.find_spec("rapidocr_onnxruntime")
    if ocr_spec is None or Path(ocr_spec.origin).resolve().parent != ocr_root:
        raise ValueError("RapidOCR import resolves outside the verified distribution")
    actual_ocr = {
        "rapidocr_onnxruntime/"
        + str(path.relative_to(ocr_root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in ocr_root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }
    if actual_ocr != ocr["package_files"]:
        raise ValueError(
            "Installed RapidOCR code or model weights differ from the staged wheel"
        )
    requirements = ocr_distribution.requires or []
    if not any(
        value.startswith("opencv-python-headless") for value in requirements
    ) or any(value.startswith("opencv-python>=") for value in requirements):
        raise ValueError("RapidOCR dependency metadata does not select headless OpenCV")
    try:
        metadata.distribution("opencv-python")
    except metadata.PackageNotFoundError:
        pass
    else:
        raise ValueError("Conflicting desktop OpenCV distribution is installed")
    for name, expected in receipt["nltk_assets"].items():
        if (
            hashlib.sha256((runtime / "nltk-data" / name).read_bytes()).hexdigest()
            != expected
        ):
            raise ValueError("Warp English resources differ from the staged assets")
    return receipt


def _worker(input_path, output_path, options):
    runtime = Path(os.environ["WARP_RUNTIME_ROOT"])
    receipt = _verify_runtime(runtime)
    os.environ["NLTK_DATA"] = str(runtime / "nltk-data")
    import nltk

    nltk.data.path[:] = [os.environ["NLTK_DATA"]]
    for resource in (
        "tokenizers/punkt/english.pickle",
        "tokenizers/punkt_tab/english/",
        "corpora/stopwords",
    ):
        nltk.data.find(resource, paths=nltk.data.path)
    import pymupdf
    from warp_ingest.file_parser import ocr_parser
    from warp_ingest.ingestor.pdf_ingestor import parse_to_opencontracts

    if not options["disable_ocr"] and not ocr_parser.ocr_available():
        raise ValueError("The selected Warp OCR backend is unavailable")
    source = input_path.read_bytes()
    with pymupdf.open(stream=source, filetype="pdf") as pdf:
        if pdf.needs_pass or not pdf.page_count:
            raise ValueError("Warp needs an unlocked nonempty PDF")
        dimensions = [(page.rect.width, page.rect.height) for page in pdf]
    raw = parse_to_opencontracts(str(input_path), options)
    export = warp_export({"result": raw}, dimensions, "")
    packages = {
        name: metadata.version(name)
        for name in (
            "warp-ingest",
            "nltk",
            "pdfplumber",
            "pdfminer.six",
            "numpy",
            "pypdfium2",
            "pymupdf",
            "opencv-python-headless",
        )
    }
    if not options["disable_ocr"]:
        packages.update(
            {
                name: metadata.version(name)
                for name in ("rapidocr-onnxruntime", "onnxruntime")
            }
        )
    revision = {
        "runtime": receipt,
        "packages": packages,
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "converter_sha256": hashlib.sha256(
            Path(__file__).with_name("parser_exports.py").read_bytes()
        ).hexdigest(),
    }
    value = {
        "export": export,
        "provenance": {
            "parser": "Warp-Ingest Local",
            "parser_version": VERSION,
            "parser_revision_sha256": hashlib.sha256(canonical(revision)).hexdigest(),
            "source_sha256": hashlib.sha256(source).hexdigest(),
            "configuration": options,
            "packages": packages,
            "patches": receipt["patches"],
            "wheel_sha256": receipt["wheel_sha256"],
        },
    }
    output_path.write_bytes(canonical(value))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--options", required=True)
    args = parser.parse_args()
    _worker(args.input, args.output, json.loads(args.options))
