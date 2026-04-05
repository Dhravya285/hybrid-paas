import NextAuth from "next-auth";
import type { DefaultSession } from "next-auth";
import GitHubProvider from "next-auth/providers/github";

declare module "next-auth" {
    interface Session {
        accessToken?: string
        backendToken?: string          // ← add this
        user?: DefaultSession["user"]
    }
}

declare module "next-auth/jwt" {
    interface JWT {
        accessToken?: string
        backendToken?: string          // ← add this
    }
}

const handler = NextAuth({
    providers: [
        GitHubProvider({
            clientId: process.env.CLIENT_ID!,
            clientSecret: process.env.CLIENT_SECRET!,
            authorization: {
                params: { scope: "read:user user:email repo" }
            }
        })
    ],
    callbacks: {
        async jwt({ account, token }) {
            if (account) {
                token.accessToken = account.access_token

                // ← exchange GitHub token for FastAPI JWT once at login
                const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/auth/github/callback`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ code: account.access_token }),
                })
                const data = await res.json()
                token.backendToken = data.access_token
            }
            return token
        },

        async session({ session, token }) {
            session.accessToken = token.accessToken
            session.backendToken = token.backendToken  // ← add this
            return session
        }
    }
})

export { handler as GET, handler as POST }