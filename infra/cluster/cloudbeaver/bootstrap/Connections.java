package medilab.cloudbeaver;

import com.google.gson.JsonObject;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.HashSet;

public final class Connections {
    private static final String CONNECTIONS_KEY = "connections";
    private static final String MANAGED_ID = "medilab-postgres";
    private static final String PRESERVED = "Existing MediLab connection preserved.";

    private static final class Blocked extends IllegalStateException {
        Blocked(String reason) {
            super(reason);
        }
    }

    public static void main(String[] args) {
        try {
            Workspace.state(Workspace.root());
            Path path = Workspace.root().resolve("GlobalConfiguration/.dbeaver/data-sources.json");
            if (Files.isDirectory(path.getParent()) && managed(path.getParent())) {
                System.out.println(PRESERVED);
                return;
            }
            JsonObject data = Files.exists(path) ? JsonFiles.read(path) : new JsonObject();
            if (!data.has(CONNECTIONS_KEY)) {
                data.add(CONNECTIONS_KEY, new JsonObject());
            }
            JsonObject connections = data.getAsJsonObject(CONNECTIONS_KEY);
            if (connections.has(MANAGED_ID)) {
                System.out.println(PRESERVED);
                return;
            }
            connections.add(MANAGED_ID, connection());
            if (Files.exists(path)) {
                backup(path);
            }
            JsonFiles.write(path, data);
            System.out.println("Missing MediLab connection provisioned.");
        } catch (Exception e) {
            String reason = e instanceof Blocked ? e.getMessage() : e.getClass().getSimpleName();
            System.err.println("CloudBeaver connection provisioning blocked (" + reason
                + "). Review workspace JSON and Secret key presence; no existing connection was replaced.");
            System.exit(1);
        }
    }

    // Scans every data-sources file, because a supplemental file can already hold the managed connection.
    private static boolean managed(Path directory) throws IOException {
        var identifiers = new HashSet<String>();
        boolean managed = false;
        try (var files = Files.newDirectoryStream(directory, "data-sources*.json")) {
            for (Path file : files) {
                if (Files.isSymbolicLink(file)) {
                    throw new Blocked("Symbolic link in data-sources");
                }
                JsonObject document = JsonFiles.read(file);
                if (document.has(CONNECTIONS_KEY)) {
                    for (String identifier : document.getAsJsonObject(CONNECTIONS_KEY).keySet()) {
                        if (!identifiers.add(identifier)) {
                            throw new Blocked("Duplicate connection identifier");
                        }
                        managed |= identifier.equals(MANAGED_ID);
                    }
                }
            }
        }
        return managed;
    }

    private static JsonObject connection() {
        String user = System.getenv("DB_USER");
        String password = System.getenv("DB_PASSWORD");
        if (user == null || user.isEmpty() || password == null || password.isEmpty()) {
            throw new Blocked("DB_USER or DB_PASSWORD missing");
        }
        JsonObject auth = new JsonObject();
        auth.addProperty("userName", user);
        auth.addProperty("userPassword", password);
        JsonObject config = new JsonObject();
        config.addProperty("host", System.getenv().getOrDefault("DB_HOST", "medilab-db-rw"));
        config.addProperty("port", "5432");
        config.addProperty("database", "medilab");
        config.addProperty("configurationType", "MANUAL");
        config.addProperty("auth-model", "native");
        config.add("auth-properties", auth);
        JsonObject connection = new JsonObject();
        connection.addProperty("provider", "postgresql");
        connection.addProperty("driver", "postgres-jdbc");
        connection.addProperty("name", "MediLab");
        connection.addProperty("save-password", true);
        connection.add("configuration", config);
        return connection;
    }

    private static void backup(Path path) throws IOException {
        Path backup = Files.createTempFile(path.getParent(), ".medilab-before-provision-", ".json",
            PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")));
        Files.write(backup, Files.readAllBytes(path));
        JsonFiles.sync(backup);
    }
}
