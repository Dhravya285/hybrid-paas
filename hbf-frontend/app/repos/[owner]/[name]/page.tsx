"use client";

import { useSession } from "next-auth/react";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { API_BASE_URL } from "../../../../lib/api";

const DEFAULT_ECR_REPOSITORY_URI =
  process.env.NEXT_PUBLIC_ECR_REPOSITORY_URI ??
  "945219712463.dkr.ecr.us-east-1.amazonaws.com/hybrid-paas";

type DeployState = "idle" | "running" | "success" | "error";

type RepoDetails = {
  full_name: string;
  description: string | null;
  stargazers_count: number;
  forks_count: number;
  watchers_count: number;
  language: string | null;
  html_url: string;
};

type Branch = {
  name: string;
};

type TreeItem = {
  path: string;
};

type DeployStreamPayload = {
  type: "status" | "log" | "result";
  status?: string;
  message?: string;
  image_uri?: string;
};

const manifestCandidates = [
  "package.json",
  "next.config.js",
  "next.config.mjs",
  "next.config.ts",
  "Dockerfile",
];

function getRootFolders(tree: TreeItem[]): string[] {
  const roots = new Set<string>();

  for (const item of tree) {
    if (!item?.path) continue;
    const manifest = manifestCandidates.find(
      (candidate) => item.path === candidate || item.path.endsWith(`/${candidate}`)
    );

    if (!manifest) continue;

    const suffix = `/${manifest}`;
    const root = item.path.endsWith(suffix)
      ? item.path.slice(0, -suffix.length) || "/"
      : "/";
    roots.add(root || "/");
  }

  if (roots.size === 0) {
    roots.add("/");
  }

  return Array.from(roots).sort((a, b) => {
    if (a === "/") return -1;
    if (b === "/") return 1;
    return a.localeCompare(b);
  });
}

function getDefaultCommands(): { build: string; run: string } {
  return {
    build: "npm run build",
    run: "npm start",
  };
}

function sanitizeRepositorySegment(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^[-.]+|[-.]+$/g, "");
}

function buildProjectRepositoryUri(baseRepositoryUri: string, owner: string, repo: string): string {
  const trimmed = baseRepositoryUri.trim().replace(/\/+$/, "");
  const ownerSegment = sanitizeRepositorySegment(owner);
  const repoSegment = sanitizeRepositorySegment(repo);

  if (!trimmed || !ownerSegment || !repoSegment) {
    return trimmed;
  }

  return `${trimmed}/${ownerSegment}/${repoSegment}`;
}

function sanitizeImageTag(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^[-.]+|[-.]+$/g, "");
}

function createDefaultImageTag(branch: string): string {
  const branchSegment = (sanitizeImageTag(branch) || "main").slice(0, 60);
  const now = new Date();
  const timestamp = [
    now.getUTCFullYear(),
    String(now.getUTCMonth() + 1).padStart(2, "0"),
    String(now.getUTCDate()).padStart(2, "0"),
  ].join("") + "-" + [
    String(now.getUTCHours()).padStart(2, "0"),
    String(now.getUTCMinutes()).padStart(2, "0"),
    String(now.getUTCSeconds()).padStart(2, "0"),
  ].join("");

  return `${branchSegment}-${timestamp}`;
}

export default function RepoPage() {
  const { owner, name } = useParams<{ owner: string; name: string }>();
  const { data: session } = useSession();
  const logsRef = useRef<HTMLPreElement | null>(null);
  const commandsInitializedRef = useRef(false);

  const [data, setData] = useState<RepoDetails | null>(null);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [selectedBranch, setSelectedBranch] = useState<string>("");
  const [tree, setTree] = useState<TreeItem[]>([]);
  const [selectedRoot, setSelectedRoot] = useState<string>("/");
  const [buildCommand, setBuildCommand] = useState<string>("npm run build");
  const [runCommand, setRunCommand] = useState<string>("npm start");
  const [imageTag, setImageTag] = useState<string>("");
  const [awsRegion, setAwsRegion] = useState<string>("");
  const [deployState, setDeployState] = useState<DeployState>("idle");
  const [deployLogs, setDeployLogs] = useState<string[]>([]);
  const [deployResult, setDeployResult] = useState<string>("");

  const rootFolders = getRootFolders(tree);
  const targetRepositoryUri = buildProjectRepositoryUri(
    DEFAULT_ECR_REPOSITORY_URI,
    owner,
    name
  );

  useEffect(() => {
    if (!owner || !name || !session?.accessToken) return;

    fetch(`https://api.github.com/repos/${owner}/${name}`, {
      headers: {
        Authorization: `Bearer ${session.accessToken}`,
      },
    })
      .then((res) => res.json())
      .then((repoData: RepoDetails) => setData(repoData));
  }, [owner, name, session]);

  useEffect(() => {
    if (!owner || !name || !session?.accessToken) return;

    fetch(`https://api.github.com/repos/${owner}/${name}/branches`, {
      headers: {
        Authorization: `Bearer ${session.accessToken}`,
      },
    })
      .then((res) => res.json())
      .then((branchData: Branch[]) => {
        setBranches(branchData);
        setSelectedBranch(branchData[0]?.name || "");
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
      .then((res: { tree?: TreeItem[] }) => {
        const nextTree = Array.isArray(res.tree) ? res.tree : [];
        const nextRoots = getRootFolders(nextTree);
        const nextRoot = nextRoots.includes(selectedRoot)
          ? selectedRoot
          : (nextRoots[0] || "/");

        setTree(nextTree);

        if (nextRoot !== selectedRoot) {
          setSelectedRoot(nextRoot);
        }

        if (!commandsInitializedRef.current || nextRoot !== selectedRoot) {
          const defaults = getDefaultCommands();
          setBuildCommand(defaults.build);
          setRunCommand(defaults.run);
          commandsInitializedRef.current = true;
        }
      });
  }, [owner, name, selectedBranch, selectedRoot, session]);

  useEffect(() => {
    logsRef.current?.scrollTo({
      top: logsRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [deployLogs]);

  useEffect(() => {
    if (!selectedBranch) return;
    setImageTag(createDefaultImageTag(selectedBranch));
  }, [selectedBranch]);

  if (!data) {
    return (
      <div className="flex h-screen items-center justify-center text-white">
        Loading...
      </div>
    );
  }

  const handleDeploy = async () => {
    try {
      const token = localStorage.getItem("token");
      if (!token) {
        setDeployState("error");
        setDeployResult("Backend auth token not found. Sign in again.");
        return;
      }

      if (!DEFAULT_ECR_REPOSITORY_URI.trim()) {
        setDeployState("error");
        setDeployResult("ECR repository is not configured.");
        return;
      }

      setDeployState("running");
      setDeployLogs(["Starting deployment..."]);
      setDeployResult("");

      const response = await fetch(`${API_BASE_URL}/deploy/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          owner,
          repo: name,
          branch: selectedBranch,
          source_dir: selectedRoot,
          build_command: buildCommand.trim() || null,
          run_command: runCommand.trim() || null,
          ecr_repository_uri: DEFAULT_ECR_REPOSITORY_URI,
          image_tag: imageTag.trim() || null,
          aws_region: awsRegion.trim() || null,
        }),
      });

      if (!response.ok || !response.body) {
        const errorText = await response.text();
        setDeployState("error");
        setDeployResult(errorText || "Deployment request failed");
        setDeployLogs((current) => [...current, errorText || "Deployment request failed"]);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let receivedResult = false;

      const applyPayload = (payload: DeployStreamPayload) => {
        if (payload.type === "log" && payload.message) {
          const message = payload.message;
          setDeployLogs((current) => [...current, message]);
        }

        if (payload.type === "result") {
          receivedResult = true;
          if (payload.status === "success") {
            setDeployState("success");
            setDeployResult(`Pushed image: ${payload.image_uri}`);
          } else {
            setDeployState("error");
            setDeployResult(payload.message || "Deployment failed");
          }
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n");
        buffer = parts.pop() || "";

        for (const part of parts) {
          if (!part.trim()) continue;
          applyPayload(JSON.parse(part) as DeployStreamPayload);
        }
      }

      if (buffer.trim()) {
        applyPayload(JSON.parse(buffer) as DeployStreamPayload);
      }

      if (!receivedResult) {
        setDeployState("error");
        setDeployResult("Deployment stream closed before a final result was returned.");
      }
    } catch (error) {
      setDeployState("error");
      setDeployResult("Deployment request failed.");
      setDeployLogs((current) => [
        ...current,
        error instanceof Error ? error.message : "Unknown deployment error",
      ]);
    }
  };

  return (
    <div className="flex min-h-screen gap-20 px-10 py-10 text-white lg:px-16">
      <div className="w-full lg:w-1/2">
        <div>
          <h1 className="mb-3 text-2xl font-semibold">{data.full_name}</h1>

          <p className="mb-6 text-gray-400">
            {data.description || "No description provided"}
          </p>

          <div className="mb-6 flex gap-6 text-sm text-gray-300">
            <span>stars - {data.stargazers_count}</span>
            <span>forks - {data.forks_count}</span>
            <span>views - {data.watchers_count}</span>
          </div>

          <p className="mb-6 text-sm text-gray-400">
            {data.language || "No primary language"}
          </p>

          <a
            href={data.html_url}
            target="_blank"
            rel="noreferrer"
            className="text-sm text-gray-300 underline hover:text-white"
          >
            View on GitHub
          </a>
        </div>
      </div>

      <div className="w-full max-w-xl lg:w-1/2">
        <h2 className="mb-6 text-lg font-semibold">Deploy</h2>

        <div className="mb-5">
          <p className="mb-2 text-sm text-gray-400">Branch</p>
          <select
            value={selectedBranch}
            onChange={(e) => setSelectedBranch(e.target.value)}
            className="w-full rounded border border-gray-700 bg-transparent px-3 py-2"
          >
            {branches.map((branch) => (
              <option key={branch.name} value={branch.name} className="text-black">
                {branch.name}
              </option>
            ))}
          </select>
        </div>

        <div className="mb-5">
          <p className="mb-2 text-sm text-gray-400">Next.js Source Folder</p>
          <select
            value={selectedRoot}
            onChange={(e) => {
              const nextRoot = e.target.value;
              const defaults = getDefaultCommands();
              setSelectedRoot(nextRoot);
              setBuildCommand(defaults.build);
              setRunCommand(defaults.run);
            }}
            className="w-full rounded border border-gray-700 bg-transparent px-3 py-2"
          >
            {rootFolders.map((folder) => (
              <option key={folder} value={folder} className="text-black">
                {folder}
              </option>
            ))}
          </select>
        </div>

        <div className="mb-5">
          <p className="mb-2 text-sm text-gray-400">Build Command</p>
          <input
            value={buildCommand}
            onChange={(e) => setBuildCommand(e.target.value)}
            placeholder="npm run build"
            className="w-full rounded border border-gray-700 bg-transparent px-3 py-2"
          />
        </div>

        <div className="mb-5">
          <p className="mb-2 text-sm text-gray-400">Run Command</p>
          <input
            value={runCommand}
            onChange={(e) => setRunCommand(e.target.value)}
            placeholder="npm start"
            className="w-full rounded border border-gray-700 bg-transparent px-3 py-2"
          />
        </div>

        <div className="mb-5">
          <p className="mb-2 text-sm text-gray-400">Target ECR Repository</p>
          <div className="w-full rounded border border-gray-700 bg-black/20 px-3 py-2 text-sm text-gray-200">
            {targetRepositoryUri}
          </div>
        </div>

        <div className="mb-5 grid gap-5 md:grid-cols-2">
          <div>
            <p className="mb-2 text-sm text-gray-400">Image Tag</p>
            <input
              value={imageTag}
              onChange={(e) => setImageTag(e.target.value)}
              placeholder="branch-YYYYMMDD-HHMMSS"
              className="w-full rounded border border-gray-700 bg-transparent px-3 py-2"
            />
          </div>

          <div>
            <p className="mb-2 text-sm text-gray-400">AWS Region</p>
            <input
              value={awsRegion}
              onChange={(e) => setAwsRegion(e.target.value)}
              placeholder="Optional if included in ECR URI"
              className="w-full rounded border border-gray-700 bg-transparent px-3 py-2"
            />
          </div>
        </div>

        <button
          onClick={handleDeploy}
          disabled={deployState === "running"}
          className="w-full rounded bg-white py-2 text-black transition hover:bg-gray-300 disabled:cursor-not-allowed disabled:bg-gray-500"
        >
          {deployState === "running" ? "Deploying..." : "Deploy"}
        </button>

        <div className="mt-6">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-sm text-gray-400">Deployment Logs</p>
            <span className="text-xs uppercase tracking-wide text-gray-400">
              {deployState}
            </span>
          </div>

          <pre
            ref={logsRef}
            className="h-80 overflow-y-auto rounded border border-gray-800 bg-black/40 p-4 text-xs text-gray-200"
          >
            {deployLogs.length > 0 ? deployLogs.join("\n") : "Logs will appear here."}
          </pre>

          {deployResult ? (
            <p
              className={`mt-3 text-sm ${
                deployState === "success" ? "text-green-400" : "text-red-400"
              }`}
            >
              {deployResult}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
