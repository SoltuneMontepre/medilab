// A release build that takes updates, whose downloads and restarts the tests plan.
export const isEnabled = true;
export const runtimeVersion: string | null = "runtime-1";
export const fetchUpdateAsync = jest.fn();
export const reloadAsync = jest.fn();
