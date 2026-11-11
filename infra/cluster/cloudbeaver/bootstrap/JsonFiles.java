import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonParser;
import com.google.gson.Strictness;
import com.google.gson.stream.JsonReader;
import com.google.gson.stream.JsonToken;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.PosixFilePermissions;

final class JsonFiles {
    static JsonObject read(Path path) throws Exception {
        try (var reader = new JsonReader(Files.newBufferedReader(path, StandardCharsets.UTF_8))) {
            reader.setStrictness(Strictness.LENIENT);
            JsonObject result = element(reader).getAsJsonObject();
            if (reader.peek() != JsonToken.END_DOCUMENT) {
                throw new IllegalArgumentException("Trailing configuration data");
            }
            return result;
        }
    }

    private static JsonElement element(JsonReader reader) throws Exception {
        if (reader.peek() == JsonToken.BEGIN_OBJECT) {
            JsonObject object = new JsonObject();
            reader.beginObject();
            while (reader.hasNext()) {
                String name = reader.nextName();
                if (object.has(name)) {
                    throw new IllegalArgumentException("Duplicate configuration key");
                }
                object.add(name, element(reader));
            }
            reader.endObject();
            return object;
        }
        if (reader.peek() == JsonToken.BEGIN_ARRAY) {
            JsonArray array = new JsonArray();
            reader.beginArray();
            while (reader.hasNext()) {
                array.add(element(reader));
            }
            reader.endArray();
            return array;
        }
        return JsonParser.parseReader(reader);
    }

    static void sync(Path path) throws Exception {
        try (var channel = FileChannel.open(path, Files.isDirectory(path) ? StandardOpenOption.READ : StandardOpenOption.WRITE)) {
            channel.force(true);
        }
    }

    static void write(Path path, JsonObject value) throws Exception {
        Files.createDirectories(path.getParent());
        Path temporary = Files.createTempFile(path.getParent(), ".medilab-", ".tmp",
            PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")));
        try {
            Files.writeString(temporary, new GsonBuilder().setPrettyPrinting().serializeNulls().create().toJson(value) + "\n");
            sync(temporary);
            Files.move(temporary, path, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            sync(path.getParent());
        } finally {
            Files.deleteIfExists(temporary);
        }
    }
}
