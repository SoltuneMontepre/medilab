import { Pressable, StyleSheet, Text, View } from "react-native";

import type { MessageKey } from "../../i18n";
import { useT } from "../../locale";
import { colors } from "../../styles";

export interface ListTab<L extends string> {
  list: L;
  label: MessageKey;
  empty: MessageKey;
}

/** The tabs of a screen that shows one of several lists, such as the to-do list's open, finished and queued tasks. */
export function ListTabs<L extends string>({
  tabs,
  chosen,
  onChoose,
}: Readonly<{ tabs: ListTab<L>[]; chosen: L; onChoose: (list: L) => void }>) {
  const t = useT();
  return (
    <View accessibilityRole="tablist" style={styles.tabs}>
      {tabs.map((item) => (
        <Pressable
          key={item.list}
          accessibilityRole="tab"
          accessibilityState={{ selected: item.list === chosen }}
          style={[styles.tab, item.list === chosen && styles.selected]}
          onPress={() => onChoose(item.list)}
        >
          <Text style={[styles.tabText, item.list === chosen && styles.selectedText]}>{t(item.label)}</Text>
        </Pressable>
      ))}
    </View>
  );
}

/** The list of the tabs the screen opens on: the one its address names, otherwise the first. */
export function chosenTab<L extends string>(tabs: ListTab<L>[], named: string | undefined): L {
  return (tabs.find((item) => item.list === named) ?? tabs[0]).list;
}

const styles = StyleSheet.create({
  tabs: { flexDirection: "row", gap: 8 },
  tab: { flex: 1, borderWidth: 1, borderColor: colors.primary, borderRadius: 8, paddingVertical: 8, alignItems: "center" },
  selected: { backgroundColor: colors.primary },
  tabText: { color: colors.primary, fontWeight: "500" },
  selectedText: { color: "#ffffff" },
});
