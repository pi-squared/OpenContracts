import { DocumentChildModal } from "../../../knowledge_base/document/LayoutComponents";
import { MouseEvent, useState, useEffect, SyntheticEvent } from "react";
import _ from "lodash";

import {
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
  Dropdown,
} from "@os-legal/ui";
import type { DropdownOption } from "@os-legal/ui";
import { useCorpusState } from "../../context/CorpusAtom";
import { ServerTokenAnnotation } from "../../types/annotations";

interface EditLabelModalProps {
  annotation: ServerTokenAnnotation;
  visible: boolean;
  onHide: () => void;
}

export const EditLabelModal = ({
  annotation,
  visible,
  onHide,
}: EditLabelModalProps) => {
  const { setCorpus, humanSpanLabels: spanLabels } = useCorpusState();

  const [selectedLabel, setSelectedLabel] = useState(
    annotation.annotationLabel
  );

  // There are onMouseDown listeners on the <canvas> that handle the
  // creation of new annotations. We use this function to prevent that
  // from being triggered when the user engages with other UI elements.
  const onMouseDown = (e: MouseEvent) => {
    e.stopPropagation();
  };

  useEffect(() => {
    if (!visible) return;
    const onKeyPress = (e: KeyboardEvent) => {
      if (/^[1-9]$/.test(e.key)) {
        const index = Number.parseInt(e.key) - 1;
        if (index < spanLabels.length) {
          e.preventDefault();
          e.stopPropagation();
          // Note: You'll need to implement updateAnnotation functionality separately
          setCorpus({
            humanSpanLabels: spanLabels.map((label, i) =>
              i === index ? selectedLabel : label
            ),
          });
          onHide();
        }
      }
    };
    window.addEventListener("keydown", onKeyPress);
    return () => {
      window.removeEventListener("keydown", onKeyPress);
    };
  }, [visible, spanLabels, annotation]);

  const dropdownOptions: DropdownOption[] = spanLabels.map((label) => ({
    value: label.id,
    label: label.text || "",
  }));

  const handleDropdownChange = (value: string | string[] | null) => {
    const labelId = typeof value === "string" ? value : null;
    const label = spanLabels.find((l) => l.id === labelId);
    if (!label) {
      return;
    }
    setSelectedLabel(label);
  };

  return (
    <DocumentChildModal open={visible} onClose={onHide}>
      <ModalHeader>Edit Label</ModalHeader>
      <ModalBody>
        <div onMouseDown={onMouseDown}>
          <Dropdown
            mode="select"
            placeholder="Select label"
            searchable="local"
            options={dropdownOptions}
            onChange={handleDropdownChange}
            value={selectedLabel.id}
          />
        </div>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="secondary"
          onMouseDown={onMouseDown}
          onClick={(e: SyntheticEvent) => {
            e.stopPropagation();
            onHide();
          }}
        >
          Cancel
        </Button>
        <Button
          variant="primary"
          onMouseDown={(e: React.MouseEvent) => e.stopPropagation()}
          onClick={(event: SyntheticEvent) => {
            event.preventDefault();
            event.stopPropagation();

            setCorpus({
              humanSpanLabels: spanLabels.map((label, i) =>
                i === spanLabels.indexOf(selectedLabel) ? selectedLabel : label
              ),
            });

            onHide();
          }}
        >
          Save Change
        </Button>
      </ModalFooter>
    </DocumentChildModal>
  );
};
