import com.google.gson.JsonObject;
import java.net.URI;
import java.nio.file.Path;

public final class Readiness {
    public static void main(String[] args) {
        try {
            if (!Workspace.runtimeComplete(Workspace.root()) || !Workspace.databaseExists(Workspace.root())) {
                throw new IllegalStateException();
            }
            check(URI.create("http://127.0.0.1:8978/api/gql"), Path.of("/bootstrap-bin/readiness-cookie"));
            Authentication.verify(
                new GraphClient(URI.create("http://127.0.0.1:8978/api/gql"), Path.of("/bootstrap-bin/readiness-cookie")),
                Path.of("/bootstrap-bin/verification-failed"));
        } catch (Exception e) {
            System.err.println("CloudBeaver readiness requires completed setup and verified administrator access. Check verification credentials and the failure latch.");
            System.exit(1);
        }
    }

    static void check(URI uri, Path cookie) throws Exception {
        var data = new GraphClient(uri, cookie).query("{ serverConfig { configurationMode } }", new JsonObject());
        var mode = data.getAsJsonObject("serverConfig").get("configurationMode");
        if (!mode.isJsonPrimitive() || !mode.getAsJsonPrimitive().isBoolean() || mode.getAsBoolean()) {
            throw new IllegalStateException();
        }
    }
}
