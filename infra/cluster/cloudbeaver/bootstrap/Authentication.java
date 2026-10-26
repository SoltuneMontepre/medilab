import com.google.gson.JsonObject;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Locale;

final class Authentication {
    static void verify(GraphClient client, Path failure) throws Exception {
        String name = System.getenv("CB_VERIFY_NAME");
        String password = System.getenv("CB_VERIFY_PASSWORD");
        if (name == null || name.isBlank() || password == null || password.isEmpty()) {
            throw new IllegalStateException();
        }
        boolean authenticated = authenticated(client, name);
        if (!authenticated) {
            if (Files.exists(failure)) {
                throw new IllegalStateException();
            }
            // A failed login is latched until application restart to avoid lockout from probe retries.
            Files.createFile(failure,
                PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")));
            JsonObject credentials = new JsonObject();
            credentials.addProperty("user", name);
            // CloudBeaver 26.2.2 requires uppercase MD5 in its local authentication protocol.
            credentials.addProperty("password", HexFormat.of().withUpperCase()
                .formatHex(MessageDigest.getInstance("MD5").digest(password.getBytes(StandardCharsets.UTF_8))));
            JsonObject variables = new JsonObject();
            variables.add("credentials", credentials);
            client.query("query($credentials: Object!) { authLogin(provider: \"local\", credentials: $credentials) { authStatus } }",
                variables);
            if (!authenticated(client, name)) {
                throw new IllegalStateException();
            }
        }
        JsonObject identity = new JsonObject();
        identity.addProperty("id", name.toLowerCase(Locale.ROOT));
        var data = client.query("query($id: ID!) { adminUserInfo(userId: $id) { enabled } "
            + "userConnections(projectId: \"g_GlobalConfiguration\") { id } }", identity);
        var enabled = data.getAsJsonObject("adminUserInfo").get("enabled");
        if (!enabled.isJsonPrimitive() || !enabled.getAsJsonPrimitive().isBoolean() || !enabled.getAsBoolean()
            || data.getAsJsonArray("userConnections") == null) {
            throw new IllegalStateException();
        }
        Files.deleteIfExists(failure);
    }

    private static boolean authenticated(GraphClient client, String name) throws Exception {
        var data = client.query("{ activeUser { userId isAnonymous } }", new JsonObject());
        if (data.get("activeUser").isJsonNull()) {
            return false;
        }
        var user = data.getAsJsonObject("activeUser");
        var anonymous = user.get("isAnonymous");
        if (!anonymous.isJsonPrimitive() || !anonymous.getAsJsonPrimitive().isBoolean()) {
            throw new IllegalStateException();
        }
        if (anonymous.getAsBoolean()) {
            return false;
        }
        if (!user.get("userId").getAsString().equals(name.toLowerCase(Locale.ROOT))) {
            throw new IllegalStateException();
        }
        return true;
    }
}
