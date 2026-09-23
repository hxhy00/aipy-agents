import pLimit from "p-limit"

const limit = pLimit(10)

export const schema = {
	name: "ip",
	description: "IP情报查询",
	inputSchema: {
		type: "object",
		properties: {
			entities: {
				type: "array",
				items: { type: "string", description: "要查询的IP地址" },
				description: "要查询的IP地址列表，支持批量查询，最多支持100个IP",
			},
			fields: {
				type: "string",
				description: "要查询的字段，多个字段用逗号分隔。例如：ip,addr,threat_level,tags",
			},
		},
		required: ["entities"],
	},
	// outputSchema: {
	// 	type: "object",
	// 	properties: {
	// 		ip: { type: "string", description: "IP地址" },
	// 		asn: { type: "string", description: "IP所属ASN" },
	// 		addr: { type: "array", items: { type: "string" }, description: "IP所属地址" },
	// 		location: { type: "object", description: "IP所属位置坐标" },
	// 		continent: { type: "string", description: "IP所属位置大洲" },
	// 		country_code: { type: "string", description: "IP所属位置国家代码" },
	// 		timezone: { type: "string", description: "IP所属位置时区" },
	// 		zipcode: { type: "string", description: "IP所属位置邮编" },
	// 		isp: { type: "string", description: "IP所属运营商", example: "电信" },
	// 		threat_level: { type: "string", description: "IP威胁度，危险IP会标记为“低危”，“中危”，“高危”。1最低，3最高。" },
	// 		ib_score: { type: "number", description: "IP智脑评分，分值越高，威胁性越大。最高100" },
	// 		tags: { type: "array", items: { type: "string" }, description: "IP攻击行为标签数据" },
	// 		active_date: { type: "string", description: "最近活跃时间" },
	// 		attack_hosts_cnt: { type: "number", description: "智脑监测到总的攻击网站数" },
	// 		attack_total: { type: "number", description: "智脑监测到总的攻击次数" },
	// 		attack_type: { type: "object", description: "攻击手段，如恶意扫描、SQL注入等等" },
	// 		attack_trend: { type: "object	", description: "IP历史活跃记录" },
	// 		attack_industry: { type: "object", description: "IP攻击过的行业分类" },
	// 		user_agent: { type: "object", description: "IP常用user_agent记录" },
	// 		access_trend: { type: "object", description: "智脑监测到IP的正常访问趋势" },
	// 		access_industry: { type: "object", description: "IP各行业正常访问分布" },
	// 		key_period: { type: "array", items: { type: "string" }, description: "IP在如“两会”，“春节”，“国庆”等重点时期攻击活跃记录" },
	// 		recon: { type: "array", items: { type: "string" }, description: "对攻击前期行为，如扫描后台，访问敏感文件等行为进行跟踪分析。" },
	// 		free_attack_tool: { type: "array", items: { type: "string" }, description: "识别攻击者使用的免费武器软件" },
	// 		commercial_attack_tool: { type: "array", items: { type: "string" }, description: "识别攻击者使用的商用武器软件" },
	// 		cloud_scanner: { type: "array", items: { type: "string" }, description: "识别是否为云扫描器" },
	// 		exploit: { type: "array", items: { type: "string" }, description: "漏洞识别规则化，精细化到CVE、CNVD编号。" },
	// 		install_backdoor: { type: "array", items: { type: "string" }, description: "后门植入" },
	// 		c2_control: { type: "array", items: { type: "string" }, description: "连接C2、CS服务器" },
	// 		webshell_control: { type: "array", items: { type: "string" }, description: "Webshell连接工具" },
	// 		dark_industry: { type: "array", items: { type: "string" }, description: "IP黑产行为记录" },
	// 		out_of_band_assets: { type: "array", items: { type: "string" }, description: "带外域名" },
	// 		proxy_relate: { type: "array", items: { type: "string" }, description: "代理服务" },
	// 		tor_trace: { type: "array", items: { type: "string" }, description: "IP有暗网活动痕迹" },
	// 		tg_robot: { type: "array", items: { type: "string" }, description: "Telegram机器人" },
	// 		ddos_attack: { type: "array", items: { type: "string" }, description: "DDoS攻击" },
	// 		command_exec: { type: "array", items: { type: "string" }, description: "IP命令执行记录" },
	// 		pentest_ability: { type: "number", description: "渗透能力值，分值越高，能力越强。最高100" },
	// 		actual_ip: { type: "array", items: { type: "string" }, description: "攻击者真实IP" },
	// 		os_type: { type: "array", items: { type: "string" }, description: "攻击者操作系统" },
	// 		use_language: { type: "array", items: { type: "string" }, description: "攻击者擅长的攻击语言" },
	// 		attack_period: { type: "string", description: "活跃时段", example: "上午" },
	// 		whois: { type: "object", description: "Whois 信息" },
	// 		device_type: { type: "string", description: "设备类型" },
	// 		os: { type: "string", description: "操作系统" },
	// 		hostname: { type: "string", description: "主机名" },
	// 		ports: { type: "object", description: "端口信息" },
	// 	},
	// 	required: ["ip"],
	// }
}

export async function handler({ entities, fields }) {
	let API = `${process.env.TRUSTOKEN_API}/aio-api/gac/v2/info/ip`
	let API_KEY = process.env.TRUSTOKEN_API_KEY
	if (process.env.GAC_API_KEY && !process.env.GAC_API_KEY.startsWith("${")) {
		API = "https://gac.yunaq.com/api/v2/info/ip"
		API_KEY = process.env.GAC_API_KEY
	}

	const headers = process.env.AIPY_HEADERS ? JSON.parse(process.env.AIPY_HEADERS) : {}

	const result = await Promise.allSettled(entities.map(entity => limit(async () => {
		const api = `${API}/${entity}/?${fields ? new URLSearchParams({ fields }) : ""}`
		const resposne = await fetch(api, {
			method: "GET",
			headers: {
				...headers,
				"Authorization": `Bearer ${API_KEY}`,
			},
		})
		if (!resposne.ok) {
			const errorText = await resposne.text()
			console.error("Error response from IP info API:", api)
			return {
				isError: true,
				content: [
					{
						type: "text",
						text: `[${resposne.status}] ${resposne.statusText}. ${errorText}`,
					}
				]
			}
		}

		const { data } = await resposne.json()

		return {
			type: "text",
			text: JSON.stringify(data || {})
		}
	})))

	return {
		content: result.reduce((acc, r) => r.status === "fulfilled" ? acc.concat(r.value) : acc, []),
	}
}
