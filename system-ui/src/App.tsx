import { useState } from "react";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import { isAuthenticated } from "./services/auth";

function App() {
  const [authenticated, setAuthenticated] = useState(isAuthenticated());

  if (!authenticated) {
    return <Login onSuccess={() => setAuthenticated(true)} />;
  }

  return <Dashboard />;
}

export default App;
