"use client"

import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import React, { useEffect, useState } from 'react'

import { API_BASE_URL } from '../../lib/api'

type RepoSummary = {
    id: number
    name: string
    full_name: string
    description: string | null
    owner: {
        login: string
    }
}

export default function Repos() {
    const {data:session} = useSession()
    
    const [repos,setRepos]= useState<RepoSummary[]>([])

    const router = useRouter()

    useEffect(() => {
        const fetchRepos = async () => {
            const token = localStorage.getItem("token");
            if (!token) return;
    
            const res = await fetch(`${API_BASE_URL}/repos`, {
                headers: {
                    Authorization: `Bearer ${token}`,
                },
            });
    
            const data = await res.json();
            setRepos(data);
        };

        if (session) {
            fetchRepos();
        }
    }, [session]);

    return (
        
          <div className="overflow-y-auto p-4">
            {repos.map((repo) => (
                <div
                  key={repo.id}
                  className="border rounded-lg p-4 mb-3 cursor-pointer hover:bg-gray-100 hover:text-black transition"
                  onClick={()=>router.push(`/repos/${repo.owner.login}/${repo.name}`)}
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
