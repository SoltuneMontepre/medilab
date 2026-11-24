import { useState, type ReactElement, type ReactNode } from "react";
import { ActivityIndicator, FlatList, RefreshControl, StyleSheet, View } from "react-native";

import type { Load } from "../../load";
import { useT } from "../../locale";
import { colors, space } from "../../theme";
import { LoadNotice } from "../connection/LoadNotice";
import { EmptyState } from "./EmptyState";
import type { IconName } from "./Icon";
import { content } from "./Screen";

/** The records of a list screen, as the web's kanban cards: read again when pulled down, the next page read once the
 * person scrolls to the end, and what the list says when it is empty, under the icon of what it lists. Until the first
 * page is read, the list says why it is not shown. */
export function RecordList<T>({
  load,
  items,
  keyOf,
  renderItem,
  icon,
  empty,
  gone = empty,
  onRetry,
  onRefresh,
  hasMore = false,
  onMore,
  header,
  footer,
}: Readonly<{
  load: Load<unknown>;
  items: T[];
  keyOf: (item: T) => string | number;
  renderItem: (item: T) => ReactElement;
  icon: IconName;
  empty: string;
  gone?: string;
  onRetry: () => void;
  onRefresh: () => Promise<unknown>;
  hasMore?: boolean;
  onMore?: () => Promise<unknown>;
  header?: ReactElement;
  footer?: ReactNode;
}>) {
  const t = useT();
  const [refreshing, setRefreshing] = useState(false);
  const [reading, setReading] = useState(false);

  async function pull() {
    setRefreshing(true);
    try {
      await onRefresh();
    } finally {
      setRefreshing(false);
    }
  }

  async function next() {
    if (!hasMore || !onMore || reading) {
      return;
    }
    setReading(true);
    try {
      await onMore();
    } finally {
      setReading(false);
    }
  }

  if (load.state !== "ready") {
    return (
      <View style={content}>
        {header}
        <LoadNotice load={load} gone={gone} onRetry={onRetry} />
      </View>
    );
  }
  return (
    <FlatList
      testID="record-list"
      data={items}
      keyExtractor={(item) => String(keyOf(item))}
      renderItem={({ item }) => renderItem(item)}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
      ListHeaderComponent={header}
      ListEmptyComponent={<EmptyState icon={icon} text={empty} />}
      ListFooterComponent={
        <>
          {reading && <ActivityIndicator color={colors.primary} accessibilityLabel={t("loading")} />}
          {footer}
        </>
      }
      onEndReached={next}
      onEndReachedThreshold={0.4}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={pull} colors={[colors.primary]} tintColor={colors.primary} />
      }
    />
  );
}

const styles = StyleSheet.create({
  content: { ...content, paddingTop: space.md, paddingBottom: space.xl, flexGrow: 1 },
});
