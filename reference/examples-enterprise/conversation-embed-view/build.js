
import tailwind from "bun-plugin-tailwind";

await Bun.build({
	entrypoints: ["src/client/index.html"],
	outdir: "./public",
	plugins: [tailwind],
	minify: true,
});
