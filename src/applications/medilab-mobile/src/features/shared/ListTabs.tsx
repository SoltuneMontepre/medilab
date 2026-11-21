import { Pressable, ScrollView, StyleSheet, Text } from "react-native";

import type { MessageKey } from "../../i18n";
import { useT } from "../../locale";
import { colors, fontSize, radius, space } from "../../theme";

export interface ListTab<L extends string> {
  list: L;
  label: MessageKey;
  empty: MessageKey;
}

/** The filters of a screen that shows one of several lists, such as the to-do list's open, finished and queued tasks,
 * as pills like the web's search facets. */
export function ListTabs<L extends string>({
  tabs,
  chosen,
  onChoose,
}: Readonly<{ tabs: ListTab<L>[]; chosen: L; onChoose: (list: L) => void }>) {
  const t = useT();
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      accessibilityRole="tablist"
      style={styles.scroller}
      contentContainerStyle={styles.tabs}
    >
      {tabs.map((item) => {
        const selected = item.list === chosen;
        return (
          <Pressable
            key={item.list}
            accessibilityRole="tab"
            accessibilityState={{ selected }}
            testID={`list-${item.list}`}
            hitSlop={6}
            style={[styles.tab, selected && styles.selected]}
            onPress={() => onChoose(item.list)}
          >
            <Text style={[styles.text, selected && styles.selectedText]}>{t(item.label)}</Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

/** The list of the tabs the screen opens on: the one its address names, otherwise the first. */
export function chosenTab<L extends string>(tabs: ListTab<L>[], named: string | undefined): L {
  return (tabs.find((item) => item.list === named) ?? tabs[0]).list;
}

const styles = StyleSheet.create({
  scroller: { flexGrow: 0 },
  tabs: { gap: space.sm, paddingHorizontal: space.lg, paddingTop: space.md, paddingBottom: space.xs },
  tab: {
    minHeight: 36,
    justifyContent: "center",
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    backgroundColor: colors.surface,
    paddingHorizontal: space.lg,
  },
  selected: { backgroundColor: colors.primary, borderColor: colors.primary },
  text: { fontSize: fontSize.base, fontWeight: "500", color: colors.textSecondary },
  selectedText: { color: colors.textOnPrimary, fontWeight: "600" },
});
