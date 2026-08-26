import { useState } from "react";
import { useLocation } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { searchDoctors, type DoctorRanked } from "../../lib/api/endpoints/doctors";
import { createAppointment, type AppointmentCreateResponse } from "../../lib/api/endpoints/appointments";
import { useAuthStore } from "../../store/auth";
import { useCaptcha } from "../../hooks/useCaptcha";
import { qk } from "../../lib/queryKeys";
import { isValidPincode } from "../../lib/format";
import { ApiError } from "../../lib/api/errors";

interface LocationState {
  specialty?: string;
  severityEsi?: number;
}

export function useBooking() {
  const location = useLocation();
  const state = (location.state as LocationState | null) ?? {};
  const patientId = useAuthStore((s) => s.user?.patientId);
  const queryClient = useQueryClient();
  const captcha = useCaptcha();

  const [specialty] = useState(state.specialty ?? "general_medicine");
  const [pincode, setPincode] = useState("");
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [locationDenied, setLocationDenied] = useState(false);
  const [selectedDoctorId, setSelectedDoctorId] = useState<string | null>(null);
  const [bookingResult, setBookingResult] = useState<AppointmentCreateResponse | null>(null);
  const [bookingError, setBookingError] = useState<string | null>(null);

  const doctorsQuery = useQuery({
    queryKey: qk.doctors({ specialty, pincode: pincode || undefined, lat: coords?.lat, lng: coords?.lng }),
    queryFn: () => searchDoctors({ specialty, lat: coords?.lat, lng: coords?.lng }),
  });

  function useMyLocation() {
    if (!navigator.geolocation) {
      setLocationDenied(true);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => setLocationDenied(true),
      { timeout: 8000 },
    );
  }

  const bookMutation = useMutation({
    mutationFn: async (doctor: DoctorRanked) => {
      if (!patientId) throw new Error("no patient profile");
      if (!captcha.token) throw new Error("captcha token missing");
      return createAppointment(
        {
          patient_id: patientId,
          specialty,
          lat: coords?.lat,
          lng: coords?.lng,
          doctor_id: doctor.doctor_id,
          severity_esi: state.severityEsi ?? 4,
        },
        captcha.token,
      );
    },
    onSuccess: (res) => {
      setBookingResult(res);
      setBookingError(null);
      void queryClient.invalidateQueries({ queryKey: ["doctors"] });
    },
    onError: (err) => {
      captcha.onRefresh();
      if (err instanceof ApiError && err.code === "CONFLICT") {
        setBookingError("that slot was just taken; pick another doctor or refresh");
        void queryClient.invalidateQueries({ queryKey: qk.doctors({ specialty }) });
        return;
      }
      setBookingError(err instanceof Error ? err.message : String(err));
    },
  });

  function selectDoctor(doctorId: string) {
    setSelectedDoctorId(doctorId);
    setBookingResult(null);
    setBookingError(null);
  }

  function bookSelected() {
    const doctor = doctorsQuery.data?.find((d) => d.doctor_id === selectedDoctorId);
    if (!doctor) return;
    bookMutation.mutate(doctor);
  }

  return {
    specialty,
    pincode,
    setPincode,
    isValidPincode: isValidPincode(pincode),
    useMyLocation,
    hasLocation: Boolean(coords),
    locationDenied,
    doctors: doctorsQuery.data ?? [],
    doctorsLoading: doctorsQuery.isLoading,
    doctorsError: doctorsQuery.error,
    selectedDoctorId,
    selectDoctor,
    bookSelected,
    booking: bookMutation.isPending,
    bookingResult,
    bookingError,
    captcha,
  };
}
