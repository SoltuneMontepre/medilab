import { memoryFiles } from "../src/testing/memoryFiles";

type Place = string | File | Directory;

function address(parts: Place[]): string {
  return parts.map((part) => (typeof part === "string" ? part : part.uri)).join("/");
}

// A file of the phone, kept in memory.
export class File {
  readonly uri: string;

  constructor(...parts: Place[]) {
    this.uri = address(parts);
  }

  get name(): string {
    return this.uri.slice(this.uri.lastIndexOf("/") + 1);
  }

  get exists(): boolean {
    return memoryFiles.has(this.uri);
  }

  create(): void {
    memoryFiles.set(this.uri, "");
  }

  async write(content: string): Promise<void> {
    memoryFiles.set(this.uri, content);
  }

  async text(): Promise<string> {
    return memoryFiles.get(this.uri) ?? "";
  }

  async base64(): Promise<string> {
    return btoa(memoryFiles.get(this.uri) ?? "");
  }

  async move(destination: File): Promise<void> {
    memoryFiles.set(destination.uri, memoryFiles.get(this.uri) ?? "");
    memoryFiles.delete(this.uri);
  }

  delete(): void {
    memoryFiles.delete(this.uri);
  }
}

// A folder of the phone; it exists once a file is in it.
export class Directory {
  readonly uri: string;

  constructor(...parts: Place[]) {
    this.uri = address(parts);
  }

  get exists(): boolean {
    return true;
  }

  create(): void {}

  list(): File[] {
    return [...memoryFiles.keys()]
      .filter((uri) => uri.startsWith(`${this.uri}/`) && !uri.slice(this.uri.length + 1).includes("/"))
      .map((uri) => new File(uri));
  }
}

export const Paths = { document: new Directory("file:///documents") };
