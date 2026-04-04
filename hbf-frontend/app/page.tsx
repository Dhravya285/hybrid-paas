"use client";

import { signIn, signOut, useSession } from "next-auth/react";
import { useRouter } from "next/navigation";

export default function Home() {
  const { data: session } = useSession();
  const router = useRouter()

  return (
    <div className="h-screen flex items-center justify-center">
      {session ? (
        <div className="flex flex-col items-center gap-4">
          <img src={session.user?.image as string} className="rounded-2xl size-50" />
          <h1>Signed in as {session.user?.name}</h1>
          <button 
            className="px-4 py-2 bg-black text-white rounded"
            onClick={()=>router.push('/repos')}
          >
            Check out ur Repos
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