import Constants from "expo-constants";

import { DEFAULT_SERVER_URL } from "../app.config";

// The MediLab address built into the app, from app.config.ts.
export const serverUrl: string = Constants.expoConfig?.extra?.serverUrl ?? DEFAULT_SERVER_URL;

// True when the build was made for a MediLab served over HTTP, so even its production build may reach one.
export const allowsHttp: boolean = Constants.expoConfig?.extra?.allowsHttp ?? false;
