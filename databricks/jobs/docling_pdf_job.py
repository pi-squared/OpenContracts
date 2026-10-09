"""Run one source-bound Docling PDF conversion outside the Databricks kernel."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

VERSION = "2.132.0"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def request(path):
    path = path.resolve()
    data = json.loads(path.read_text())
    directory = path.parent
    if (
        not str(directory).startswith("/Volumes/")
        or directory.name != data["attempt_id"]
        or directory.parent.name != "attempts"
        or Path(data["source_path"]).resolve() != directory / "source.pdf"
        or Path(data["output_directory"]).resolve() != directory / "result"
    ):
        raise ValueError("Invalid source-bound Docling attempt paths")
    if digest(directory / "source.pdf") != data["source_sha256"]:
        raise ValueError("Docling input PDF hash differs from its request")
    if set(data["options"]) != {"do_ocr", "do_table_structure"} or any(
        type(value) is not bool for value in data["options"].values()
    ):
        raise ValueError("Unsupported Docling parser options")
    return data, directory


def convert(manifest):
    data, directory = request(manifest)
    output = directory / "result"
    started = time.monotonic()
    receipt = {
        "attempt_id": data["attempt_id"],
        "source_sha256": data["source_sha256"],
        "parser_version": VERSION,
        "options": data["options"],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "installed_packages": {
            name: importlib.metadata.version(name)
            for name in (
                "docling-slim",
                "docling-core",
                "docling-parse",
                "docling-ibm-models",
                "rapidocr",
                "onnxruntime",
                "opencv-python-headless",
                "numpy",
                "torch",
                "torchvision",
                "transformers",
                "pypdfium2",
                "huggingface-hub",
            )
        },
        "job_script_sha256": digest(Path(__file__)),
        "converter_sha256": digest(Path(__file__).with_name("parser_exports.py")),
        "status": "running",
        "model_asset_revisions": None,
    }
    save(output / "receipt.json", receipt)
    try:
        if importlib.metadata.version("docling-slim") != VERSION:
            raise ValueError("The Docling distribution differs from the pinned recipe")
        import pypdfium2
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (
            PdfPipelineOptions,
            RapidOcrOptions,
        )
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from parser_exports import docling_export

        options = PdfPipelineOptions(ocr_options=RapidOcrOptions(), **data["options"])
        receipt["pipeline_options"] = options.model_dump(
            mode="json", serialize_as_any=True
        )
        save(output / "receipt.json", receipt)
        converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
        )
        result = converter.convert(directory / "source.pdf", raises_on_error=False)
        raw = {
            "status": result.status.value,
            "errors": [error.model_dump(mode="json") for error in result.errors],
            "document": result.document.export_to_dict(),
        }
        save(output / "raw-document.json", raw)
        if raw["status"] != "success":
            raise ValueError("Docling did not successfully convert the complete PDF")
        pdf = pypdfium2.PdfDocument(str(directory / "source.pdf"))
        try:
            dimensions = []
            for index in range(len(pdf)):
                page = pdf[index]
                try:
                    dimensions.append(page.get_size())
                finally:
                    page.close()
        finally:
            pdf.close()
        export = docling_export(raw, dimensions, data["title"])
        if export["page_count"] != len(dimensions):
            raise ValueError("Docling page coverage differs from the original PDF")
        if digest(directory / "source.pdf") != data["source_sha256"]:
            raise ValueError("Original PDF changed during Docling conversion")
        save(output / "export.json", export)
        snapshots = directory.parents[1] / "model-cache" / "huggingface" / "hub"
        # Cache inventory does not prove which model revision conversion used.
        receipt["available_model_snapshots"] = (
            sorted(
                str(p.relative_to(snapshots))
                for p in snapshots.glob("models--*/snapshots/*")
                if p.is_dir()
            )
            or None
        )
        receipt.update(
            status="success",
            page_count=len(dimensions),
            export_sha256=digest(output / "export.json"),
            raw_output_sha256=digest(output / "raw-document.json"),
        )
    except Exception:
        (output / "error.txt").write_text(traceback.format_exc())
        receipt["status"] = "failed"
        raise
    finally:
        receipt["seconds"] = time.monotonic() - started
        receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
        save(output / "receipt.json", receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--child", action="store_true")
    # Spark Python tasks are exec'd by IPython without defining __file__.
    # Pass the immutable worker path explicitly to launch ordinary Python.
    parser.add_argument("--worker-file", type=Path)
    args = parser.parse_args()
    data, directory = request(args.manifest)
    if args.child:
        convert(args.manifest)
        return
    output = directory / "result"
    if output.exists():
        receipt = json.loads((output / "receipt.json").read_text())
        if (
            receipt.get("status") == "success"
            and receipt.get("attempt_id") == data["attempt_id"]
            and receipt.get("source_sha256") == data["source_sha256"]
            and receipt.get("options") == data["options"]
            and digest(output / "export.json") == receipt.get("export_sha256")
        ):
            return
        raise ValueError(
            "Retained Docling attempt is incomplete or failed; parser work is not replayed"
        )
    output.mkdir()
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    cache = directory.parents[1] / "model-cache"
    environment.update(
        HF_HOME=str(cache / "huggingface"),
        DOCLING_CACHE_DIR=str(cache / "docling"),
        OMP_NUM_THREADS="4",
        OPENBLAS_NUM_THREADS="4",
    )
    with (output / "stdout.log").open("xb") as stdout, (output / "stderr.log").open(
        "xb"
    ) as stderr:
        process = subprocess.run(
            [
                sys.executable,
                "-X",
                "faulthandler",
                str((args.worker_file or Path(sys.argv[0])).resolve()),
                "--child",
                "--manifest",
                str(args.manifest),
            ],
            env=environment,
            stdout=stdout,
            stderr=stderr,
            timeout=3300,
        )
    if process.returncode:
        receipt_file = output / "receipt.json"
        receipt = (
            json.loads(receipt_file.read_text())
            if receipt_file.exists()
            else {
                "attempt_id": data["attempt_id"],
                "source_sha256": data["source_sha256"],
            }
        )
        receipt.update(
            status="failed",
            child_exit_code=process.returncode,
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        save(receipt_file, receipt)
        raise RuntimeError(
            "Docling child process failed; private attempt logs are retained"
        )


if __name__ == "__main__":
    main()
