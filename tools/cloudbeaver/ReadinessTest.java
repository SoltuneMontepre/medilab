import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.file.Files;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public final class ReadinessTest {
    public static void main(String[] args) throws Exception {
        var status = new AtomicInteger(200);
        var response = new AtomicReference<>("{\"data\":{\"serverConfig\":{\"configurationMode\":false}}}");
        var cookieSeen = new AtomicReference<String>();
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/api/gql", exchange -> {
            cookieSeen.set(exchange.getRequestHeaders().getFirst("Cookie"));
            var bytes = response.get().getBytes(java.nio.charset.StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Set-Cookie", "probe=regression; HttpOnly; Path=/");
            exchange.sendResponseHeaders(status.get(), bytes.length);
            exchange.getResponseBody().write(bytes);
            exchange.close();
        });
        server.start();
        var directory = Files.createTempDirectory("readiness-test-");
        var cookie = directory.resolve("cookie");
        var uri = URI.create("http://127.0.0.1:" + server.getAddress().getPort() + "/api/gql");
        try {
            Readiness.check(uri, cookie);
            Readiness.check(uri, cookie);
            if (!"probe=regression".equals(cookieSeen.get())) {
                throw new AssertionError("Probe must reuse its session cookie");
            }
            for (String body : new String[] {
                "{\"data\":{\"serverConfig\":{\"configurationMode\":true}}}",
                "{\"errors\":[],\"data\":{\"serverConfig\":{\"configurationMode\":false}}}",
                "{\"errors\":[{\"message\":\"failure\"}]}",
                "{\"data\":{\"serverConfig\":{\"configurationMode\":\"false\"}}}",
                "{\"data\":null}", "{}", "not json"
            }) {
                response.set(body);
                reject(uri, cookie);
            }
            response.set("{\"data\":{\"serverConfig\":{\"configurationMode\":false}}}");
            status.set(503);
            reject(uri, cookie);
            status.set(302);
            reject(uri, cookie);
        } finally {
            server.stop(0);
            Files.deleteIfExists(cookie);
            Files.delete(directory);
        }
        reject(uri, cookie);
        System.out.println("Readiness rejects setup, GraphQL errors, invalid bodies, redirects, HTTP errors and connection failure; session reused.");
    }

    static void reject(URI uri, java.nio.file.Path cookie) throws Exception {
        try {
            Readiness.check(uri, cookie);
        } catch (Exception expected) {
            return;
        }
        throw new AssertionError("Incomplete or unavailable server accepted");
    }
}
