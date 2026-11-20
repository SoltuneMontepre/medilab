import { useState, type ReactNode } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { useT } from "../../locale";
import { colors, layout, radius, space } from "../../theme";
import { BottomSheet } from "./BottomSheet";
import { Button, type Tone } from "./Button";
import { Icon, type IconName } from "./Icon";

/** An action of a record, coloured by what it does. */
export interface BarAction {
  key: string;
  label: string;
  onPress: () => void;
  tone?: Tone;
  icon?: IconName;
  disabled?: boolean;
  testID?: string;
}

// The buttons the bar shows; the others wait behind its "more" button.
const SHOWN = 2;

/** The actions of a record at the bottom of its screen, where they stay while it scrolls: the first two as buttons, the
 * main one first, and the others in a sheet the "more" button opens. What a screen shows above the buttons, such as why
 * the last action did not happen, comes as `children`. */
export function ActionBar({ actions, children }: Readonly<{ actions: BarAction[]; children?: ReactNode }>) {
  const t = useT();
  const [more, setMore] = useState(false);
  const shown = actions.slice(0, SHOWN);
  const hidden = actions.slice(SHOWN);
  if (!actions.length && !children) {
    return null;
  }
  return (
    <SafeAreaView edges={["bottom", "left", "right"]} style={styles.bar}>
      <View style={styles.inner}>
        {children}
        {actions.length > 0 && (
          <View style={styles.row}>
            {shown.map((action) => (
              <View key={action.key} style={styles.slot}>
                <Button
                  label={action.label}
                  tone={action.tone}
                  icon={action.icon}
                  disabled={action.disabled}
                  testID={action.testID}
                  onPress={action.onPress}
                />
              </View>
            ))}
            {hidden.length > 0 && (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={t("actions.more")}
                testID="more-actions"
                style={styles.more}
                onPress={() => setMore(true)}
              >
                <Icon name="dots-horizontal" size={24} color={colors.text} />
              </Pressable>
            )}
          </View>
        )}
      </View>
      <BottomSheet visible={more} title={t("actions.more")} onClose={() => setMore(false)}>
        {hidden.map((action) => (
          <Button
            key={action.key}
            label={action.label}
            tone={action.tone}
            icon={action.icon}
            disabled={action.disabled}
            testID={action.testID}
            onPress={() => {
              setMore(false);
              action.onPress();
            }}
          />
        ))}
      </BottomSheet>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  bar: { backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border },
  inner: {
    width: "100%",
    maxWidth: layout.contentWidth,
    alignSelf: "center",
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    gap: space.sm,
  },
  row: { flexDirection: "row", gap: space.sm },
  slot: { flex: 1 },
  more: {
    width: layout.touch,
    height: layout.touch,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.borderControl,
    alignItems: "center",
    justifyContent: "center",
  },
});
