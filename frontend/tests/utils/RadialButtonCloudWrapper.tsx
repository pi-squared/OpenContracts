import React, { useState } from "react";
import RadialButtonCloud from "../../src/components/widgets/buttons/RadialButtonCloud";
import type { CloudButtonItem } from "../../src/components/widgets/buttons/RadialButtonCloud";

interface RadialButtonCloudWrapperProps {
  actions: CloudButtonItem[];
  parentBackgroundColor?: string;
  underlay?: boolean;
}

export const RadialButtonCloudWrapper: React.FC<
  RadialButtonCloudWrapperProps
> = ({ actions, parentBackgroundColor = "#ffffff", underlay = false }) => {
  const [clicks, setClicks] = useState(0);
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        width: "300px",
        height: "300px",
        position: "relative",
      }}
    >
      {underlay && (
        <>
          <button
            aria-label="Underlying surface"
            style={{
              position: "absolute",
              inset: 0,
              width: "100%",
              height: "100%",
            }}
            onClick={() => setClicks((value) => value + 1)}
          />
          <output
            aria-label="Underlying clicks"
            style={{ position: "absolute", bottom: 8 }}
          >
            {clicks}
          </output>
        </>
      )}
      <RadialButtonCloud
        parentBackgroundColor={parentBackgroundColor}
        actions={actions}
      />
    </div>
  );
};
