import { useFocusEffect } from "expo-router";
import { useCallback, useRef } from "react";

/** Reads the screen again when the person returns to it, such as after acting on a task it lists; its first reading
 * is the screen's own. */
export function useReloadOnReturn(reload: () => unknown) {
  const opened = useRef(false);
  useFocusEffect(
    useCallback(() => {
      if (opened.current) {
        reload();
      }
      opened.current = true;
    }, [reload]),
  );
}
