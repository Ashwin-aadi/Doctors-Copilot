import { LineChart, Line, YAxis } from "recharts";
import type { LabTrendPoint } from "../types";

export interface LabTrendSparklineProps {
  points: LabTrendPoint[];
  /** Whether a rising value is the bad direction for this test. */
  higherIsWorse?: boolean;
  label?: string;
  className?: string;
}

/**
 * A 24x40 trend, no axes, no tooltip -- it exists to show direction at a
 * glance next to the value. Rendered only when there are at least two points;
 * a single reading is not a trend.
 */
export function LabTrendSparkline({
  points,
  higherIsWorse = true,
  label,
  className,
}: LabTrendSparklineProps) {
  if (points.length < 2) return null;

  const first = points[0].value;
  const last = points[points.length - 1].value;
  const rising = last > first;
  const worsening = rising === higherIsWorse;
  const stroke = last === first ? "var(--fg-muted)" : worsening ? "var(--critical)" : "var(--normal)";

  const direction = last === first ? "unchanged" : rising ? "rising" : "falling";
  const description = `${label ? `${label}: ` : ""}${direction} across ${points.length} readings, latest ${last}`;

  return (
    <span
      role="img"
      aria-label={description}
      className={className}
      style={{ display: "inline-block", width: 24, height: 40 }}
    >
      {/* Fixed 24x40, so the chart is sized directly rather than through a
          ResponsiveContainer -- one less resize observer per row in a table
          that can hold dozens of them. */}
      <LineChart
        width={24}
        height={40}
        data={points}
        margin={{ top: 4, right: 0, bottom: 4, left: 0 }}
      >
        <YAxis hide domain={["dataMin", "dataMax"]} />
        <Line
          type="monotone"
          dataKey="value"
          stroke={stroke}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </span>
  );
}
