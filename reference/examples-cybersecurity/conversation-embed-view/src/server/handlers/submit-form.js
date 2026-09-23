const AIPY_CLIENT_API = process.env.AIPY_CLIENT_API
const AIPY_CLIENT_API_KEY = process.env.AIPY_CLIENT_API_KEY

/** @type {import("express").RequestHandler} */
export async function submitForm(req, res) {
  try {
    const { name, email, message } = req.body

    // 验证必填字段
    if (!name || !email) {
      return res.status(400).json({ error: "姓名和邮箱为必填项" })
    }

    // 构造任务指令
    const instruction = `用户提交了信息收集表单：
- 姓名：${name}
- 邮箱：${email}
- 备注：${message || "无"}

请根据以上信息执行后续任务。`

    console.log("Sending task to AiPy...")

    // 调用 AiPy API 创建任务
    const createRes = await fetch(`${AIPY_CLIENT_API}/api/aipy/create-task`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${AIPY_CLIENT_API_KEY}`
      },
      body: JSON.stringify([{
        instruction,
      }])
    })

    if (!createRes.ok) {
      throw new Error(`创建任务失败: ${await createRes.text()}`)
    }

    const createData = await createRes.json()
    const taskId = createData.data

    console.log(`Task created: ${taskId}`)

    // 导航到新创建的任务页面
    const navigateRes = await fetch(`${AIPY_CLIENT_API}/api/browser/navigate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${AIPY_CLIENT_API_KEY}`
      },
      body: JSON.stringify([`/task/${taskId}`])
    })

    if (!navigateRes.ok) {
      console.error(`导航失败: ${await navigateRes.text()}`)
    }

    // 发送关闭嵌入页面消息
    console.log(JSON.stringify({
      type: "client/conversation-embed-view",
      action: "close"
    }))

    // 延迟退出，确保消息已发送
    setTimeout(() => {
      process.exit(0)
    }, 300)

    res.json({ success: true, message: "任务已下发", taskId })
  } catch (error) {
    console.error("Submit failed:", error)
    res.status(500).json({ error: error.message })
  }
}