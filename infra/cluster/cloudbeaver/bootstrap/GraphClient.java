import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;
import java.time.Duration;

final class GraphClient {
    private final URI uri;
    private final Path cookie;
    private final HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();

    GraphClient(URI uri, Path cookie) {
        this.uri = uri;
        this.cookie = cookie;
    }

    JsonObject query(String query, JsonObject variables) throws Exception {
        JsonObject payload = new JsonObject();
        payload.addProperty("query", query);
        payload.add("variables", variables);
        var request = HttpRequest.newBuilder(uri).timeout(Duration.ofSeconds(3))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(payload.toString()));
        if (Files.isRegularFile(cookie)) {
            request.header("Cookie", Files.readString(cookie));
        }
        var response = client.send(request.build(), HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() != 200) {
            throw new IllegalStateException();
        }
        var cookies = response.headers().allValues("set-cookie");
        if (!cookies.isEmpty()) {
            String value = cookies.stream().filter(c -> c.startsWith("cb-session-id="))
                .reduce((first, last) -> last).orElse(cookies.getLast()).split(";", 2)[0];
            if (!Files.exists(cookie)) {
                Files.createFile(cookie,
                    PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")));
            }
            Files.writeString(cookie, value);
        }
        var body = JsonParser.parseString(response.body()).getAsJsonObject();
        if (body.has("errors")) {
            throw new IllegalStateException();
        }
        return body.getAsJsonObject("data");
    }
}
