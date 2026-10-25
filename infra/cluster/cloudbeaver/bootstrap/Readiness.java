import com.google.gson.JsonParser;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;

public final class Readiness {
    public static void main(String[] args) {
        try {
            if (!Workspace.runtimeComplete(Workspace.root()) || !Workspace.databaseExists(Workspace.root())) {
                throw new IllegalStateException();
            }
            check(URI.create("http://127.0.0.1:8978/api/gql"), Path.of("/bootstrap-bin/readiness-cookie"));
        } catch (Exception e) {
            System.err.println("CloudBeaver is not initialized and ready.");
            System.exit(1);
        }
    }

    static void check(URI uri, Path cookie) throws Exception {
        var request = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofSeconds(3)).header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString("{\"query\":\"{ serverConfig { configurationMode } }\"}"));
        if (Files.isRegularFile(cookie)) {
            request.header("Cookie", Files.readString(cookie));
        }
        var response = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build()
            .send(request.build(), HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() != 200) {
            throw new IllegalStateException();
        }
        var body = JsonParser.parseString(response.body()).getAsJsonObject();
        if (body.has("errors")) {
            throw new IllegalStateException();
        }
        var mode = body.getAsJsonObject("data").getAsJsonObject("serverConfig").get("configurationMode");
        if (!mode.isJsonPrimitive() || !mode.getAsJsonPrimitive().isBoolean() || mode.getAsBoolean()) {
            throw new IllegalStateException();
        }
        var setCookie = response.headers().firstValue("set-cookie");
        if (setCookie.isPresent()) {
            Files.writeString(cookie, setCookie.get().split(";", 2)[0]);
        }
    }
}
