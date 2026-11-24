import { View } from "react-native";

// An icon draws its glyph from a font the tests do not load; the icon's name is kept to find it.
export default function MaterialCommunityIcons({ name }: Readonly<{ name: string }>) {
  return <View testID={`icon-${name}`} />;
}
