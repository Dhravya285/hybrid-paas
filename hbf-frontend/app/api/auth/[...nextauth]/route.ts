import NextAuth from "next-auth";
import type { DefaultSession } from "next-auth";
import GitHubProvider from "next-auth/providers/github";

declare module "next-auth" {
    interface Session {
        accessToken?: string
        user?: DefaultSession["user"]
    }
}

declare module "next-auth/jwt" {
    interface JWT {
        accessToken?: string
    }
}

const handler = NextAuth({
    providers:[
        GitHubProvider({
            clientId:process.env.CLIENT_ID!,
            clientSecret:process.env.CLIENT_SECRET!,
            authorization:{
                params:{
                    scope : "read:user user:email repo"
                }
            }
        })
    ],
    callbacks:{
        async jwt({account,token}){
            if(account){
                token.accessToken = account.access_token
            }
            return token
        },

        async session({session,token}){
            session.accessToken = token.accessToken
            return session
        }
    }
})

export { handler as GET, handler as POST }