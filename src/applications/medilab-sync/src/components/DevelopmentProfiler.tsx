import { Profiler, type ReactNode } from "react";
import { recordRenderProfile } from "../lib/renderProfiler";

/** Thuộc tính của wrapper đo render theo tên subtree. */
type DevelopmentProfilerProps = Readonly<{
  id: string;
  children: ReactNode;
}>;

/** Bọc subtree bằng React Profiler ở development; production trả nguyên children và không ghi log. */
export function DevelopmentProfiler({ id, children }: DevelopmentProfilerProps) {
  if (!import.meta.env.DEV) {
    return children;
  }

  return (
    <Profiler id={id} onRender={recordRenderProfile}>
      {children}
    </Profiler>
  );
}
