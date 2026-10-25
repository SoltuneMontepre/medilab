import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Locale;

public final class Workspace {
    static Path root() {
        return Path.of(System.getenv().getOrDefault("MEDILAB_WORKSPACE", "/opt/cloudbeaver/workspace"));
    }

    static boolean databaseExists(Path root) {
        Path database = root.resolve(".data/cb.h2v2.dat.mv.db");
        try {
            return Files.isRegularFile(database) && Files.size(database) > 0;
        } catch (java.io.IOException e) {
            return false;
        }
    }

    static boolean runtimeComplete(Path root) {
        try {
            var config = JsonFiles.read(root.resolve(".data/.cloudbeaver.runtime.conf"));
            var name = config.getAsJsonObject("server").get("serverName");
            return name.isJsonPrimitive() && name.getAsJsonPrimitive().isString()
                && !name.getAsString().isBlank() && !name.getAsString().contains("${");
        } catch (Exception e) {
            return false;
        }
    }

    static String state(Path root) throws Exception {
        Path runtime = root.resolve(".data/.cloudbeaver.runtime.conf");
        if (runtimeComplete(root) && databaseExists(root)) {
            return "initialized";
        }
        if (Files.exists(root.resolve(".medilab-bootstrap-attempt"))) {
            throw new IllegalStateException("Interrupted bootstrap or lost runtime configuration: review recovery on a backup clone before any retry.");
        }
        if (Files.exists(runtime) || Files.exists(root.resolve(".data")) || Files.exists(root.resolve(".metadata"))) {
            throw new IllegalStateException("Existing workspace requires recovery: runtime configuration and H2 must both be present. Bootstrap is blocked.");
        }
        String name = System.getenv().getOrDefault("CB_ADMIN_NAME", "");
        String normalized = name.toLowerCase(Locale.ROOT);
        if (name.isBlank() || !name.equals(name.strip()) || normalized.equals("admin") || normalized.equals("user")) {
            throw new IllegalStateException("Fresh bootstrap requires an administrator identifier distinct from the built-in teams admin and user.");
        }
        if (System.getenv().getOrDefault("CB_ADMIN_PASSWORD", "").isEmpty()
            || System.getenv().getOrDefault("CB_SERVER_NAME", "").isBlank()) {
            throw new IllegalStateException("Fresh bootstrap requires administrator credentials and a server name.");
        }
        return "fresh";
    }

    public static void main(String[] args) {
        try {
            Path root = root();
            String state = state(root);
            if (args.length == 1 && args[0].equals("start") && state.equals("fresh")) {
                Files.createDirectories(root);
                Files.writeString(root.resolve(".medilab-bootstrap-attempt"), "Bootstrap attempted; runtime configuration is the completion record.\n",
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            }
            System.out.println(state);
        } catch (Exception e) {
            System.err.println("CloudBeaver startup blocked. " + e.getMessage());
            System.exit(1);
        }
    }
}
