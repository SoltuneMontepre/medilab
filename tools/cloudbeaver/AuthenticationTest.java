package medilab.cloudbeaver;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class AuthenticationTest {
    // Fake CloudBeaver GraphQL endpoint whose login, health and identity answers the test switches.
    private static final class FakeServer implements HttpHandler {
        private final AtomicBoolean authenticated = new AtomicBoolean(false);
        private final AtomicBoolean failLogin = new AtomicBoolean(false);
        private final AtomicBoolean failHealth = new AtomicBoolean(false);
        private final AtomicBoolean failIdentityOnce = new AtomicBoolean(false);
        private final AtomicInteger healthMode = new AtomicInteger();
        private final AtomicInteger logins = new AtomicInteger();

        @Override
        public void handle(HttpExchange exchange) throws IOException {
            String request = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
            String body;
            int status = 200;
            if (request.contains("authLogin")) {
                body = login(exchange);
            } else if (request.contains("adminUserInfo")) {
                status = failHealth.get() ? 503 : 200;
                body = health();
            } else {
                boolean validCookie = "cb-session-id=verified".equals(exchange.getRequestHeaders().getFirst("Cookie"));
                if (authenticated.get() && failIdentityOnce.getAndSet(false)) {
                    status = 503;
                }
                body = authenticated.get() && validCookie
                    ? "{\"data\":{\"activeUser\":{\"userId\":\"operator\",\"isAnonymous\":false}}}"
                    : "{\"data\":{\"activeUser\":{\"userId\":\"@anonymous@\",\"isAnonymous\":true}}}";
            }
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(status, bytes.length);
            exchange.getResponseBody().write(bytes);
            exchange.close();
        }

        private String login(HttpExchange exchange) {
            logins.incrementAndGet();
            authenticated.set(!failLogin.get());
            exchange.getResponseHeaders().add("Set-Cookie", "cb-session-id=; Max-Age=0; Path=/");
            exchange.getResponseHeaders().add("Set-Cookie", "cb-session-id=verified; HttpOnly; Path=/");
            return failLogin.get() ? "{\"errors\":[{\"message\":\"Authentication failed\"}]}"
                : "{\"data\":{\"authLogin\":{\"authStatus\":\"SUCCESS\"}}}";
        }

        private String health() {
            String enabled = switch (healthMode.get()) {
                case 1 -> "false";
                case 2 -> "\"true\"";
                default -> "true";
            };
            String connections = healthMode.get() == 3 ? "null" : "[]";
            return "{\"data\":{\"adminUserInfo\":{\"enabled\":" + enabled
                + "},\"userConnections\":" + connections + "}}";
        }
    }

    public static void main(String[] args) throws Exception {
        var fake = new FakeServer();
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/api/gql", fake);
        var directory = Files.createTempDirectory("authentication-test-",
            PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------")));
        var cookie = directory.resolve("cookie");
        var failure = directory.resolve("failure");
        server.start();
        try {
            var client = new GraphClient(URI.create("http://127.0.0.1:" + server.getAddress().getPort() + "/api/gql"), cookie);
            Authentication.verify(client, failure);
            Authentication.verify(client, failure);
            if (fake.logins.get() != 1 || Files.exists(failure)) {
                throw new AssertionError("A successful session must be reused without a failure latch");
            }
            fake.failHealth.set(true);
            reject(client, failure);
            if (Files.exists(failure) || fake.logins.get() != 1) {
                throw new AssertionError("Transient health failures must neither latch nor authenticate again");
            }
            fake.failHealth.set(false);
            Authentication.verify(client, failure);
            for (int mode = 1; mode <= 3; mode++) {
                fake.healthMode.set(mode);
                reject(client, failure);
            }
            fake.healthMode.set(0);
            Authentication.verify(client, failure);
            if (fake.logins.get() != 1) {
                throw new AssertionError("Protected health failures must not trigger another login");
            }
            fake.authenticated.set(false);
            fake.failIdentityOnce.set(true);
            reject(client, failure);
            if (!Files.exists(failure) || fake.logins.get() != 2) {
                throw new AssertionError("Uncertain post-login verification must latch without retrying");
            }
            Authentication.verify(client, failure);
            if (Files.exists(failure) || fake.logins.get() != 2) {
                throw new AssertionError("A fully validated cached session must clear its uncertain-login latch");
            }
            fake.authenticated.set(false);
            fake.failLogin.set(true);
            reject(client, failure);
            reject(client, failure);
            if (!Files.exists(failure) || fake.logins.get() != 3) {
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
