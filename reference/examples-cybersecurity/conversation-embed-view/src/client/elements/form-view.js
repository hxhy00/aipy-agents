import { SquarkElement } from "squark"

export class FormView extends SquarkElement {
  constructor() {
    super()
    this.innerHTML = /*html*/`
      <div class="bg-white rounded-2xl shadow-lg p-6 flex flex-col h-full">
        <h1 class="text-2xl font-bold text-slate-800 mb-2">信息收集</h1>
        <p class="text-sm text-slate-500 mb-6">请填写以下信息，提交后将返回至对话流</p>

        <form class="flex-1 flex flex-col gap-4">
          <div>
            <label class="mb-1 block text-sm font-medium text-slate-700">姓名 *</label>
            <input
              type="text"
              name="name"
              required
              class="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
              placeholder="请输入姓名"
            >
          </div>

          <div>
            <label class="mb-1 block text-sm font-medium text-slate-700">邮箱 *</label>
            <input
              type="email"
              name="email"
              required
              class="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
              placeholder="请输入邮箱"
            >
          </div>

          <div class="flex-1">
            <label class="mb-1 block text-sm font-medium text-slate-700">备注（可选）</label>
            <textarea
              name="message"
              class="w-full h-full min-h-32 p-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all resize-none"
              placeholder="请输入备注信息"
            ></textarea>
          </div>

          <button
            type="submit"
            class="cursor-pointer bg-blue-600 hover:bg-blue-700 text-white font-medium py-3 px-6 rounded-xl shadow-lg shadow-blue-600/20 transition-all flex items-center justify-center gap-2"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
            提交信息
          </button>
        </form>
      </div>
    `
  }

  mount(signal) {
    const formEl = this.querySelector("form")

    formEl.addEventListener("submit", async (e) => {
      e.preventDefault()

      const formData = new FormData(e.target)
      const data = Object.fromEntries(formData.entries())

      const submitBtn = this.querySelector("button[type=submit]")
      submitBtn.disabled = true
      submitBtn.innerHTML = /*html*/`
        <svg class="animate-spin h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        提交中...
      `

      try {
        const response = await fetch("/api/submit", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data)
        })

        const result = await response.json()

        if (result.success) {
          submitBtn.innerHTML = /*html*/`
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
            提交成功
          `
          submitBtn.classList.remove("bg-blue-600", "hover:bg-blue-700", "shadow-blue-600/20")
          submitBtn.classList.add("bg-green-600")
        } else {
          throw new Error(result.error || "提交失败")
        }
      } catch (error) {
        submitBtn.disabled = false
        submitBtn.innerHTML = /*html*/`
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
          </svg>
          提交信息
        `
        alert(error.message)
      }
    }, { signal })
  }
}