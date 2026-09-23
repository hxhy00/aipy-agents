import { defineConfig, globalIgnores } from "eslint/config"
import stylistic from '@stylistic/eslint-plugin'

export default defineConfig([
	globalIgnores(["build/*"]),
	{
		files: ["server/*.js"],
		plugins: {
			'@stylistic': stylistic
		},
		rules: {
			indent: ["error", "tab", { "SwitchCase": 0 }],
			semi: ["error", "never"],
			quotes: ["error", "double"],
			camelcase: 0,
			"@stylistic/key-spacing": ["error", {
				"beforeColon": false,
				"afterColon": true,
			}],
			"@stylistic/keyword-spacing": ["error", { "before": true, "after": true }],
			"@stylistic/comma-spacing": ["error", { "before": false, "after": true }],
			"@stylistic/space-in-parens": ["error", "never"],
			"@stylistic/jsx-tag-spacing": ["error", { "beforeSelfClosing": "proportional-always" }],
			"@stylistic/jsx-quotes": ["error", "prefer-double"],
			"@stylistic/jsx-wrap-multilines": "error",
		}
	}
])
