import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class AuthenticationTest {
    public static void main(String[] args) throws Exception {
        var authenticated = new AtomicBoolean(false);
        var failLogin = new AtomicBoolean(false);
        var failHealth = new AtomicBoolean(false);
        var logins = new AtomicInteger();
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/api/gql", exchange -> {
            String request = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
            String body;
            int status = 200;
            if (request.contains("authLogin")) {
                logins.incrementAndGet();
                authenticated.set(!failLogin.get());
                exchange.getResponseHeaders().add("Set-Cookie", "cb-session-id=; Max-Age=0; Path=/");
                exchange.getResponseHeaders().add("Set-Cookie", "cb-session-id=verified; HttpOnly; Path=/");
                body = failLogin.get() ? "{\"errors\":[{\"message\":\"Authentication failed\"}]}"
                    : "{\"data\":{\"authLogin\":{\"authStatus\":\"SUCCESS\"}}}";
            } else if (request.contains("adminUserInfo")) {
                status = failHealth.get() ? 503 : 200;
                body = "{\"data\":{\"adminUserInfo\":{\"enabled\":true},\"userConnections\":[]}}";
            } else {
                boolean validCookie = "cb-session-id=verified".equals(exchange.getRequestHeaders().getFirst("Cookie"));
                body = authenticated.get() && validCookie
                    ? "{\"data\":{\"activeUser\":{\"userId\":\"operator\",\"isAnonymous\":false}}}"
                    : "{\"data\":{\"activeUser\":{\"userId\":\"@anonymous@\",\"isAnonymous\":true}}}";
            }
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(status, bytes.length);
            exchange.getResponseBody().write(bytes);
            exchange.close();
        });
        var directory = Files.createTempDirectory("authentication-test-");
        var cookie = directory.resolve("cookie");
        var failure = directory.resolve("failure");
        server.start();
        try {
            var client = new GraphClient(URI.create("http://127.0.0.1:" + server.getAddress().getPort() + "/api/gql"), cookie);
            Authentication.verify(client, failure);
            Authentication.verify(client, failure);
            if (logins.get() != 1 || Files.exists(failure)) {
                throw new AssertionError("A successful session must be reused without a failure latch");
            }
            failHealth.set(true);
            reject(client, failure);
            if (Files.exists(failure) || logins.get() != 1) {
                throw new AssertionError("Transient health failures must neither latch nor authenticate again");
            }
            failHealth.set(false);
            Authentication.verify(client, failure);
            authenticated.set(false);
            failLogin.set(true);
            reject(client, failure);
            reject(client, failure);
            if (!Files.exists(failure) || logins.get() != 2) {
                throw new AssertionError("A failed login must not be retried by subsequent probes");
            }
        } finally {
            server.stop(0);
            Files.deleteIfExists(cookie);
            Files.deleteIfExists(failure);
            Files.delete(directory);
        }
    }

    static void reject(GraphClient client, java.nio.file.Path failure) throws Exception {
        try {
            Authentication.verify(client, failure);
        } catch (Exception expected) {
            return;
        }
        throw new AssertionError("An unhealthy or unauthorized server was accepted");
    }
}
