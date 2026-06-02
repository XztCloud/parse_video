import { useRouter, useParams } from "next/navigation";
import { useEffect, useState, useCallback } from "react";


export default function ClonePage() {
    const router = useRouter();
    const params = useParams();

    const videoId = Number(params.id);
    const [error, setError] = useState<string | null>(null);
}