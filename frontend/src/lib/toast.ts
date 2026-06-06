import { toast } from "sonner";

export const notify = (msg: string) => toast.success(msg);
export const notifyError = (msg: string) => toast.error(msg);
