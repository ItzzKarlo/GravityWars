import Lobby from "@/components/Lobby";

export default async function LobbyPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  return <Lobby code={code} />;
}
