const BASE = process.env.NEXT_PUBLIC_API_URL

// call this once after login to exchange GitHub token for your FastAPI JWT
export async function loginToBackend(githubAccessToken: string) {
    const res = await fetch(`${BASE}/auth/github/callback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: githubAccessToken }),
    })
    const data = await res.json()
    if (data.access_token) {
        localStorage.setItem("hbf_token", data.access_token)
    }
    return data
}

// use this for all FastAPI calls
export function getToken() {
    return localStorage.getItem("hbf_token")
}

export async function apiFetch(path: string, options: RequestInit = {}) {
    const token = getToken()
    return fetch(`${BASE}${path}`, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            ...options.headers,
        },
    })
}