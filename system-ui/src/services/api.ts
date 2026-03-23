import axios from "axios";
import type { SystemData } from "../types/system"; // ✅ FIXED

export const fetchSystemData = async (): Promise<SystemData> => {
  const res = await axios.get("http://127.0.0.1:8000/system/summary");
  return res.data;
};
