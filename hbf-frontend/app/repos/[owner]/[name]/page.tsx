"use client";

import { useSession } from "next-auth/react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

export default function RepoPage() {
  const { owner, name } = useParams();
  const { data: session } = useSession();
  const router = useRouter();

  const [data, setData] = useState<any>();
  const [branches, setBranches] = useState<any[]>([]);
  const [selectedBranch, setSelectedBranch] = useState<string>("");
  const [tree, setTree] = useState<any[]>([]);
  const [selectedRoot, setSelectedRoot] = useState<string>("/");
  const [buildCommand, setBuildCommand] = useState("npm run build");
  const [runCommand, setRunCommand] = useState("npm start");
  const [deploying, setDeploying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!owner || !name || !session?.accessToken) return;

    fetch(`https://api.github.com/repos/${owner}/${name}`, {
      headers: {
        Authorization: `Bearer ${session.accessToken}`,
      },
    })
      .then((res) => res.json())
      .then(setData);
  }, [owner, name, session]);

  useEffect(() => {
    if (!owner || !name || !session?.accessToken) return;

    fetch(`https://api.github.com/repos/${owner}/${name}/branches`, {
      headers: {
        Authorization: `Bearer ${session.accessToken}`,
      },
    })
      .then((res) => res.json())
      .then((data) => {
        setBranches(data);
        setSelectedBranch(data[0]?.name || "");
      });
  }, [owner, name, session]);

  useEffect(() => {
    if (!owner || !name || !session?.accessToken || !selectedBranch) return;

    fetch(
      `https://api.github.com/repos/${owner}/${name}/git/trees/${selectedBranch}?recursive=1`,
      {
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
        },
      }
    )
      .then((res) => res.json())
      .then((res) => setTree(res.tree || []));
  }, [owner, name, session, selectedBranch]);

  const rootFolders = tree
    .filter((file: any) => file.path.endsWith("package.json"))
    .map((file: any) => file.path.replace("/package.json", "") || "/");

  async function handleDeploy() {
    setDeploying(true);
    setError(null);
    try {
      const res = await apiFetch("/deployments", {
        method: "POST",
        body: JSON.stringify({
          repo_url:      data.clone_url,
          repo_name:     data.name,
          owner:         owner,
          branch:        selectedBranch,
          root_dir:      selectedRoot,
          build_command: buildCommand,
          run_command:   runCommand,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        setError(err.detail || "Deployment failed");
        return;
      }

      const deployment = await res.json();
      router.push(`/deployments/${deployment.id}`);
    } catch (e) {
      setError("Could not reach server. Is FastAPI running?");
      console.error(e);
    } finally {
      setDeploying(false);
    }
  }

  if (!data)
    return (
      <div className="h-screen flex items-center justify-center text-white">
        Loading...
      </div>
    );

  return (
    <div className="h-screen flex text-white px-16 py-10 gap-20">

      {/* left — repo info */}
      <div className="w-1/2">
        <h1 className="text-2xl font-semibold mb-3">
          {data.full_name}
        </h1>

        <p className="mb-6 text-gray-400">
          {data.description || "No description provided"}
        </p>

        <div className="flex gap-6 text-sm mb-6 text-gray-300">
          <span>stars - {data.stargazers_count}</span>
          <span>forks - {data.forks_count}</span>
          <span>views - {data.watchers_count}</span>
        </div>

        <p className="text-sm text-gray-400 mb-6">
          {data.language || "No primary language"}
        </p>

        <a
          href={data.html_url}
          target="_blank"
          rel="noreferrer"
          className="text-sm underline text-gray-300 hover:text-white"
        >
          View on GitHub →
        </a>
      </div>

      {/* right — deploy form */}
      <div className="w-1/2 max-w-md">
        <h2 className="text-lg font-semibold mb-6">Deploy</h2>

        <div className="mb-5">
          <p className="text-sm mb-2 text-gray-400">Branch</p>
          <select
            value={selectedBranch}
            onChange={(e) => setSelectedBranch(e.target.value)}
            className="w-full px-3 py-2 bg-transparent border border-gray-700 rounded"
          >
            {branches.map((b: any) => (
              <option key={b.name} value={b.name} className="text-black">
                {b.name}
              </option>
            ))}
          </select>
        </div>

        <div className="mb-5">
          <p className="text-sm mb-2 text-gray-400">Root Directory</p>
          <select
            value={selectedRoot}
            onChange={(e) => setSelectedRoot(e.target.value)}
            className="w-full px-3 py-2 bg-transparent border border-gray-700 rounded"
          >
            {rootFolders.length > 0 ? (
              rootFolders.map((folder: string) => (
                <option key={folder} value={folder} className="text-black">
                  {folder || "/"}
                </option>
              ))
            ) : (
              <option value="/">/</option>
            )}
          </select>
        </div>

        <div className="mb-5">
          <p className="text-sm mb-2 text-gray-400">Build Command</p>
          <input
            value={buildCommand}
            onChange={(e) => setBuildCommand(e.target.value)}
            placeholder="npm run build"
            className="w-full px-3 py-2 bg-transparent border border-gray-700 rounded"
          />
        </div>

        <div className="mb-6">
          <p className="text-sm mb-2 text-gray-400">Run Command</p>
          <input
            value={runCommand}
            onChange={(e) => setRunCommand(e.target.value)}
            placeholder="npm start"
            className="w-full px-3 py-2 bg-transparent border border-gray-700 rounded"
          />
        </div>

        {/* error message */}
        {error && (
          <p className="text-red-400 text-sm mb-4">{error}</p>
        )}

        <button
          onClick={handleDeploy}
          disabled={deploying}
          className="w-full bg-white text-black py-2 rounded hover:bg-gray-300 transition disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {deploying ? "Deploying..." : "Deploy"}
        </button>
      </div>
    </div>
  );
}