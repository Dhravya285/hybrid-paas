"use client"

import { useSession } from 'next-auth/react'
import React, { useEffect, useState } from 'react'

export default function Repos() {
    const {data:session} = useSession()
    
    const [repos,setRepos]= useState([])

    useEffect(()=>{
        if (session?.accessToken){
            fetch("https://api.github.com/user/repos?per_page=100&sort=updated&direction=desc",{
                headers:{
                    Authorization : `Bearer ${session.accessToken}`
                }
            })
            .then((res) => res.json())
            .then(setRepos)
        }
    },[session])

    return (
        
          <div className="overflow-y-auto p-4">
            {repos.map((repo: any) => (
                <div
                  key={repo.id}
                  className="border rounded-lg p-4 mb-3 cursor-pointer hover:bg-gray-100 hover:text-black transition"
                  onClick={() => window.open(repo.html_url, "_blank")}
                >
                  <h2 className="font-semibold text-lg">{repo.full_name}</h2>
                  <p className="text-sm text-gray-500">
                    {repo.description || "No description"}
                  </p>
                </div>
                ))}
          </div>
        
    );
}
