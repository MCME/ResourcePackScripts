// Writes java_blocks.json for generateBedrock: every block of a Minecraft
// version, its block state properties, and what Bedrock has to be told about
// each state that a Java resource pack can't say - light emission, light
// dampening, and whether the client draws the state from a model at all.
//
// Run against the server jar of the version the release server converts
// (26.2 today), from the folder the jar unpacked into on its first start:
//
//     java -DbundlerMainClass=net.minecraft.data.Main -jar server.jar --reports
//     CP="versions/26.2/server-26.2.jar:$(find libraries -name '*.jar' | tr '\n' ':')"
//     javac -d dump -cp "$CP" DumpBlockStates.java
//     java -cp "dump:$CP" DumpBlockStates java_blocks.json
//
// (On Windows the separator is ; instead of :.) The first command makes the
// bundler unpack itself. Since 26.1 the server jar isn't obfuscated, so this
// compiles against its own names. docs/bedrock.md ("A new Minecraft version")
// has the steps.

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;
import net.minecraft.SharedConstants;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.RenderShape;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.Property;

public class DumpBlockStates {

    public static void main(String[] args) throws Exception {
        SharedConstants.tryDetectVersion();
        Bootstrap.bootStrap();

        // Sorted, one block per line, so a new version's file diffs block by block
        Map<String, JsonObject> blocks = new TreeMap<>();
        for (Block block : BuiltInRegistries.BLOCK) {
            JsonObject entry = new JsonObject();

            // In the order the game writes a state, minecraft:oak_leaves[distance=1,...],
            // which is the order Geyser's state keys must use
            List<Property<?>> properties = new ArrayList<>(block.getStateDefinition().getProperties());
            JsonObject propertyValues = new JsonObject();
            for (Property<?> property : properties) {
                propertyValues.add(property.getName(), values(property));
            }
            entry.add("properties", propertyValues);

            BlockState base = block.defaultBlockState();
            entry.add("default", facts(base));
            entry.addProperty("friction", block.getFriction());

            // Only the states that differ from the default state, keyed like Geyser's state_overrides
            JsonObject differing = new JsonObject();
            for (BlockState state : block.getStateDefinition().getPossibleStates()) {
                JsonArray these = facts(state);
                if (!these.equals(entry.get("default"))) {
                    differing.add(key(state, properties), these);
                }
            }
            if (!differing.isEmpty()) {
                entry.add("states", differing);
            }
            blocks.put(BuiltInRegistries.BLOCK.getKey(block).toString(), entry);
        }

        Gson gson = new GsonBuilder().disableHtmlEscaping().create();
        try (Writer out = Files.newBufferedWriter(Path.of(args[0]), StandardCharsets.UTF_8)) {
            out.write("{\"minecraft\": " + gson.toJson(SharedConstants.getCurrentVersion().name())
                    + ", \"columns\": " + gson.toJson("light_emission, light_dampening, drawn_from_model")
                    + ", \"blocks\": {\n");
            int left = blocks.size();
            for (Map.Entry<String, JsonObject> block : blocks.entrySet()) {
                out.write(gson.toJson(block.getKey()) + ": " + gson.toJson(block.getValue()) + (--left > 0 ? ",\n" : "\n"));
            }
            out.write("}}\n");
        }
    }

    // [light emission, light dampening, drawn from a block model]
    private static JsonArray facts(BlockState state) {
        JsonArray facts = new JsonArray();
        facts.add(state.getLightEmission());
        facts.add(state.getLightDampening());
        facts.add(state.getRenderShape() == RenderShape.MODEL);
        return facts;
    }

    private static <T extends Comparable<T>> JsonArray values(Property<T> property) {
        JsonArray values = new JsonArray();
        for (T value : property.getPossibleValues()) {
            values.add(property.getName(value));
        }
        return values;
    }

    private static String key(BlockState state, List<Property<?>> properties) {
        return properties.stream().map(p -> p.getName() + "=" + name(state, p)).collect(Collectors.joining(","));
    }

    private static <T extends Comparable<T>> String name(BlockState state, Property<T> property) {
        return property.getName(state.getValue(property));
    }
}
