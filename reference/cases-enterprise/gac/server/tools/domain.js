import pLimit from "p-limit"

const limit = pLimit(10)

export const schema = {
	name: "domain",
	description: "域名情报查询",
	inputSchema: {
		type: "object",
		properties: {
			entity: { type: "string", description: "要查询的域名" },
		},
		required: ["entity"],
	},
	// outputSchema: {
	// 	type: "object",
	// 	properties: {
	// 		domain: { type: "string", description: "查询的域名地址" },
	// 		domain_score: { type: "number", description: "域名智脑评分，分值越高，威胁性越大。最高100" },
	// 		threat_level: { type: "number", description: "域名威胁度，危险域名会标记为“低危”，“中危”， “高危”。1最低，3	最高" },
	// 		alexa_rank: { type: "number", description: "Alexa排序，默认值：0" },
	// 		umbrella_rank: { type: "number", description: "Umbrella排序，默认值：0" },
	// 		tags: { type: "array", items: { type: "string" }, description: "恶意域名标签数据" },
	// 		tags_type: { type: "array", items: { type: "string" }, description: "恶意域名标签类别" },
	// 		basic: { type: "object", description: "基础信息" },
	// 		industry: { type: "array", items: { type: "string" }, description: "域名分类（行业，网页内容），如互联网、网络购物等" },
	// 		sample: { type: "array", items: { type: "string" }, description: "相关样本" },
	// 		family: { type: "array", items: { type: "string" }, description: "所属恶意家族" },
	// 		whois: { type: "object", description: "域名whois信息" },
	// 	}
	// }
}

export async function handler({ entity }) {
	const API = process.env.TRUSTOKEN_API
	const API_KEY = process.env.TRUSTOKEN_API_KEY

	const headers = process.env.AIPY_HEADERS ? JSON.parse(process.env.AIPY_HEADERS) : {}

	const result = await Promise.allSettled([entity].map(entity => limit(async () => {

		const [credit, analysis] = await Promise.all([
			fetch(`${API}/aio-api/gac/v3/domain_credit/${entity}`, {
				method: "GET",
				headers: {
					...headers,
					"Authorization": `Bearer ${API_KEY}`,
				},
			}),
			fetch(`${API}/aio-api/gac/v3/domain_analysis/${entity}`, {
				method: "GET",
				headers: {
					...headers,
					"Authorization": `Bearer ${API_KEY}`,
				},
			}),
		])
		if (!credit.ok) {
			const errorText = await credit.text()
			console.error("Error response from IP info API:", entity)
			throw McpError(ErrorCode.InvalidRequest, `[${credit.status}] ${credit.statusText}. ${errorText}`)
		}
		if (!analysis.ok) {
			const errorText = await analysis.text()
			console.error("Error response from IP info API:", entity)
			throw McpError(ErrorCode.InvalidRequest, `[${analysis.status}] ${analysis.statusText}. ${errorText}`)
		}

		const data = [await credit.json().then(x => x.data), await analysis.json().then(x => x.data)]
			.reduce((acc, cur) => ({ ...acc, ...cur }), {})

		return {
			type: "text",
			text: JSON.stringify(data || {})
		}
	})))

	return {
		content: result.reduce((acc, r) => r.status === "fulfilled" ? acc.concat(r.value) : acc, []),
	}
}
