import Constants from "expo-constants";

import { DEFAULT_SERVER_URL } from "../app.config";

// The MediLab address built into the app, from app.config.ts.
export const serverUrl: string = Constants.expoConfig?.extra?.serverUrl ?? DEFAULT_SERVER_URL;
