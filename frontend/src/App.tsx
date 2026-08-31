import { useState } from "react";
import { ChatPanel } from "./components/ChatPanel";
import { InspectionSheet } from "./components/InspectionSheet";
import "./App.css";

function App() {
  const [tab, setTab] = useState<"chat" | "inspection">("chat");

  return (
    <div className="app">
      <h1>정밀안전점검·진단 교량편 QnA</h1>
      <div className="tabs">
        <button onClick={() => setTab("chat")} disabled={tab === "chat"}>채팅</button>
        <button onClick={() => setTab("inspection")} disabled={tab === "inspection"}>점검표</button>
      </div>
      {tab === "chat" ? <ChatPanel /> : <InspectionSheet />}
    </div>
  );
}

export default App;
