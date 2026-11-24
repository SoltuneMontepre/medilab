import { memo, type Dispatch, type SetStateAction } from "react";
import { StyleSheet, View, type GestureResponderEvent } from "react-native";

import { colors, radius } from "../../theme";
import { PNG_HEIGHT, PNG_WIDTH, segments, type Point, type Stroke } from "./signaturePng";

// The ink's width on the screen.
const INK = 3;

/** The box the customer signs in by hand. Each touch adds a stroke; a pad nobody draws on only shows them. */
export function SignaturePad({
  strokes,
  onDraw,
  onLayout,
  label,
}: Readonly<{
  strokes: Stroke[];
  onDraw?: Dispatch<SetStateAction<Stroke[]>>;
  onLayout?: (size: { width: number; height: number }) => void;
  label: string;
}>) {
  const point = (event: GestureResponderEvent): Point => ({
    x: event.nativeEvent.locationX,
    y: event.nativeEvent.locationY,
  });
  const drawing = onDraw !== undefined;
  return (
    <View
      accessibilityLabel={label}
      style={styles.pad}
      testID="signature-pad"
      onLayout={(event) => onLayout?.(event.nativeEvent.layout)}
      onStartShouldSetResponder={() => drawing}
      onMoveShouldSetResponder={() => drawing}
      // The screen does not scroll away a stroke being drawn.
      onResponderTerminationRequest={() => false}
      onResponderGrant={(event) => {
        const start = point(event);
        onDraw?.((drawn) => [...drawn, [start]]);
      }}
      onResponderMove={(event) => {
        const next = point(event);
        onDraw?.((drawn) => [...drawn.slice(0, -1), [...(drawn.at(-1) ?? []), next]]);
      }}
    >
      {segments(strokes).map(({ id, from, to }) => (
        <Ink key={id} from={from} to={to} />
      ))}
    </View>
  );
}

/** A piece of a stroke, from one point to the next, or a dot where a stroke starts. */
const Ink = memo(function Ink({ from, to }: Readonly<{ from: Point; to: Point }>) {
  const length = Math.hypot(to.x - from.x, to.y - from.y);
  const angle = Math.atan2(to.y - from.y, to.x - from.x);
  return (
    <View
      pointerEvents="none"
      style={[
        styles.ink,
        {
          left: (from.x + to.x) / 2 - (length + INK) / 2,
          top: (from.y + to.y) / 2 - INK / 2,
          width: length + INK,
          transform: [{ rotate: `${angle}rad` }],
        },
      ]}
    />
  );
});

const styles = StyleSheet.create({
  pad: {
    aspectRatio: PNG_WIDTH / PNG_HEIGHT,
    borderWidth: 1.5,
    borderStyle: "dashed",
    borderColor: colors.borderControl,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    overflow: "hidden",
  },
  ink: { position: "absolute", height: INK, borderRadius: INK / 2, backgroundColor: colors.text },
});
