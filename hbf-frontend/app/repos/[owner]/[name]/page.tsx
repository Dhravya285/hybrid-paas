"use client";

import { useSession } from "next-auth/react";
import { headers } from "next/headers";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

export default function RepoPage() {
  const { owner, name } = useParams();
  const {data:session}=useSession()
  const [data, setData] = useState<any>();

  useEffect(() => {
       fetch(
        `https://api.github.com/repos/${owner}/${name}`,
        {   
            headers:{
                Authorization: `Bearer ${session?.accessToken}`
            }
        }
        )
      .then((res)=> res.json())
      .then(setData)      
  }, [owner, name]);

  

  if (!data)
    return (
      <div className="h-screen flex items-center justify-center">
        <p>Loading...</p>
      </div>
    );

  return (
    <div className="h-screen flex items-center justify-center text-white">
      <div className="w-[500px] border rounded-lg p-6 shadow-sm">
        
        <h1 className="text-xl font-semibold mb-2">
          {data.full_name}
        </h1>

        <p className="text-white mb-4">
          {data.description || "No description provided"}
        </p>

        <div className="flex gap-6 text-sm text-white mb-4">
          <span>stars - {data.stargazers_count}</span>
          <span>fork - {data.forks_count}</span>
          <span>views - {data.watchers_count}</span>
        </div>

        <p className="text-sm text-white mb-4">
          {data.language || "No primary language"}
        </p>

        <a
          href={data.html_url}
          target="_blank"
          rel="noreferrer"
          className="block text-center bg-white text-black py-2 rounded hover:bg-gray-800 transition"
        >
          View on GitHub
        </a>
      </div>
    </div>
  );
}