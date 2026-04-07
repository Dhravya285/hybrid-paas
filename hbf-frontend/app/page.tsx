"use client";

import Image from "next/image";
import { signIn, signOut, useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { API_BASE_URL } from "../lib/api";

export default function Home() {
  const { data: session } = useSession();
  const router = useRouter()

  useEffect(()=>{
    const sendToken = async () =>{
      if (!session?.accessToken) return;
      const res = await fetch(`${API_BASE_URL}/auth/github`,
        {
          method:"POST",
          headers:{
            "Content-Type":"application/json"
          },
          body:JSON.stringify({
            access_token : session?.accessToken
          })
        }        
      )

      const data = await res.json();
      if (data?.access_token) {
        localStorage.setItem("token", data.access_token)
      }
    }

    sendToken()
  },[session])

  return (
    <div className="h-screen flex items-center justify-center">
      {session ? (
        <div className="flex flex-col items-center gap-4">
          <Image
            src={session.user?.image as string}
            alt={session.user?.name ? `${session.user.name} avatar` : "GitHub avatar"}
            width={200}
            height={200}
            className="rounded-2xl size-50"
          />
          <h1>Signed in as {session.user?.name}</h1>
          <button 
            className="px-4 py-2 bg-black text-white rounded"
            onClick={()=>router.push('/repos')}
          >
            Check out ur Repos
          </button>
          <button 
            className="px-4 py-2 bg-black text-white rounded"
            onClick={()=>router.push('/deployments')}
          >
            Check out ur Deployments
          </button>
          <button
            onClick={() => signOut()}
            className="px-4 py-2 bg-black text-white rounded"
          >
            Sign Out
          </button>
        </div>
      ) : (
        <button
          onClick={() => signIn("github")}
          className="px-4 py-2 bg-white text-black rounded"
        >
          Sign in with GitHub
        </button>
      )}
    </div>
  );
}
