import com.google.gson.JsonObject;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;

public final class Connections {
    private static final class Blocked extends IllegalStateException {
        Blocked(String reason) {
            super(reason);
        }
    }

    public static void main(String[] args) {
        try {
            Workspace.state(Workspace.root());
            Path path = Workspace.root().resolve("GlobalConfiguration/.dbeaver/data-sources.json");
            if (Files.isDirectory(path.getParent())) {
                var identifiers = new java.util.HashSet<String>();
                boolean managed = false;
                try (var files = Files.newDirectoryStream(path.getParent(), "data-sources*.json")) {
                    for (Path file : files) {
                        if (Files.isSymbolicLink(file)) {
                            throw new Blocked("Symbolic link in data-sources");
                        }
                        JsonObject document = JsonFiles.read(file);
                        if (document.has("connections")) {
                            for (String identifier : document.getAsJsonObject("connections").keySet()) {
                                if (!identifiers.add(identifier)) {
                                    throw new Blocked("Duplicate connection identifier");
                                }
                                managed |= identifier.equals("medilab-postgres");
                            }
                        }
                    }
                }
                if (managed) {
                    System.out.println("Existing MediLab connection preserved.");
                    return;
                }
            }
            JsonObject data = Files.exists(path) ? JsonFiles.read(path) : new JsonObject();
            JsonObject connections;
            if (data.has("connections")) {
                connections = data.getAsJsonObject("connections");
            } else {
                connections = new JsonObject();
                data.add("connections", connections);
            }
            if (connections.has("medilab-postgres")) {
                System.out.println("Existing MediLab connection preserved.");
                return;
            }
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
            connections.add("medilab-postgres", connection);
            if (Files.exists(path)) {
                Path backup = Files.createTempFile(path.getParent(), ".medilab-before-provision-", ".json",
                    PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")));
                Files.write(backup, Files.readAllBytes(path));
                JsonFiles.sync(backup);
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
}
