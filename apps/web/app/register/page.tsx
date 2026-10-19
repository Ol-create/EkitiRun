
"use client";

import { useEffect, useState, type FormEvent } from "react";
import { z } from "zod";

type RunnerDetails = {
  firstName: string;
  lastName: string;
  gender: string;
  dateOfBirth: string;
  email: string;
  phone: string;
  categoryId: string;
  emergencyContactName: string;
  emergencyContactPhone: string;
};

type RaceCategory = {
  id: string;
  code: string;
  name: string;
  distance_km: number;
  slots_left: number;
  is_full: boolean;
};

const STORAGE_KEY = "ekitirun-registration";

const DEMO_CATEGORIES: RaceCategory[] = [
  {
    id: "demo-5k",
    code: "5K",
    name: "5K Run",
    distance_km: 5,
    slots_left: 100,
    is_full: false,
  },
  {
    id: "demo-10k",
    code: "10K",
    name: "10K Run",
    distance_km: 10,
    slots_left: 100,
    is_full: false,
  },
  {
    id: "demo-half",
    code: "HALF",
    name: "Half Marathon",
    distance_km: 21.0975,
    slots_left: 100,
    is_full: false,
  },
  {
    id: "demo-full",
    code: "FULL",
    name: "Full Marathon",
    distance_km: 42.195,
    slots_left: 100,
    is_full: false,
  },
];

function normalizeNigerianPhone(phone: string): string {
  const cleaned = phone.trim().replace(/[\s()-]/g, "");

  if (/^0[789][01]\d{8}$/.test(cleaned)) {
    return `+234${cleaned.slice(1)}`;
  }

  return cleaned;
}

const nigerianPhoneSchema = z
  .string()
  .regex(
    /^\+234[789][01]\d{8}$/,
    "Enter a valid Nigerian number, e.g. 08012345678 or +2348012345678."
  );

const detailsSchema = z.object({
  firstName: z.string().trim().min(1, "First name is required."),
  lastName: z.string().trim().min(1, "Last name is required."),
  gender: z
    .string()
    .refine((value) => value === "M" || value === "F", {
      message: "Please select your gender.",
    }),
  dateOfBirth: z
    .string()
    .min(1, "Date of birth is required.")
    .refine((value) => {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;

      const date = new Date(`${value}T00:00:00`);

      return (
        !Number.isNaN(date.getTime()) &&
        date.getFullYear() === Number(value.slice(0, 4)) &&
        date.getMonth() + 1 === Number(value.slice(5, 7)) &&
        date.getDate() === Number(value.slice(8, 10)) &&
        date <= new Date()
      );
    }, "Enter a valid date of birth. It cannot be in the future."),
  email: z.union([
    z.literal(""),
    z.string().email("Enter a valid email address."),
  ]),
  phone: nigerianPhoneSchema,
});

const emergencySchema = z.object({
  emergencyContactName: z
    .string()
    .trim()
    .min(1, "Emergency contact name is required."),
  emergencyContactPhone: nigerianPhoneSchema,
});

const STORAGE_FIELDS: (keyof RunnerDetails)[] = [
  "firstName",
  "lastName",
  "gender",
  "dateOfBirth",
  "email",
  "phone",
  "categoryId",
  "emergencyContactName",
  "emergencyContactPhone",
];

const EMPTY_DETAILS: RunnerDetails = {
  firstName: "",
  lastName: "",
  gender: "",
  dateOfBirth: "",
  email: "",
  phone: "",
  categoryId: "",
  emergencyContactName: "",
  emergencyContactPhone: "",
};

export default function Page() {
  const [details, setDetails] = useState<RunnerDetails>(EMPTY_DETAILS);
  const [step, setStep] = useState(1);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [detailsSaved, setDetailsSaved] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");
  const [categoryNotice, setCategoryNotice] = useState(
    "Demo categories are being shown because the categories API is not available yet."
  );

  // Restore saved information when the page opens.
  useEffect(() => {
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY);

      if (saved) {
        const parsed: unknown = JSON.parse(saved);

        if (
          typeof parsed === "object" &&
          parsed !== null &&
          !Array.isArray(parsed)
        ) {
          const restored = { ...EMPTY_DETAILS };
          const savedObject = parsed as Record<string, unknown>;

          for (const field of STORAGE_FIELDS) {
            if (typeof savedObject[field] === "string") {
              restored[field] = savedObject[field] as never;
            }
          }

          setDetails(restored);
        }
      }
    } catch {
      try {
        sessionStorage.removeItem(STORAGE_KEY);
      } catch {
        // Storage might be disabled in the browser.
      }
    } finally {
      setDetailsSaved(true);
    }
  }, []);

  // Save all registration steps during this browser-tab session.
  useEffect(() => {
    if (!detailsSaved) return;

    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(details));
    } catch {
      // The form can still be used if storage is unavailable.
    }
  }, [details, detailsSaved]);

  function updateField(field: keyof RunnerDetails, value: string) {
    setDetails((current) => ({ ...current, [field]: value }));
    setErrors((current) => {
      const updated = { ...current };
      delete updated[field];
      return updated;
    });
    setSuccessMessage("");
  }

  function showError(field: keyof RunnerDetails) {
    return errors[field] ? (
      <p className="mt-1 text-sm text-red-600" role="alert">
        {errors[field]}
      </p>
    ) : null;
  }

  function validatePersonalDetails() {
    const result = detailsSchema.safeParse({
      ...details,
      firstName: details.firstName.trim(),
      lastName: details.lastName.trim(),
      email: details.email.trim(),
      phone: normalizeNigerianPhone(details.phone),
    });

    if (!result.success) {
      const fieldErrors: Record<string, string> = {};

      for (const issue of result.error.issues) {
        const field = String(issue.path[0]);
        if (!fieldErrors[field]) fieldErrors[field] = issue.message;
      }

      setErrors(fieldErrors);
      return false;
    }

    setDetails((current) => ({
      ...current,
      firstName: result.data.firstName,
      lastName: result.data.lastName,
      email: result.data.email,
      phone: result.data.phone,
    }));

    setErrors({});
    return true;
  }

  function validateCategory() {
    const selected = DEMO_CATEGORIES.find(
      (category) => category.id === details.categoryId
    );

    if (!selected) {
      setErrors({ categoryId: "Please choose a race category." });
      return false;
    }

    if (selected.is_full || selected.slots_left <= 0) {
      setErrors({ categoryId: "This category is full. Please choose another." });
      return false;
    }

    setErrors({});
    return true;
  }

  function validateEmergencyContact() {
    const result = emergencySchema.safeParse({
      emergencyContactName: details.emergencyContactName,
      emergencyContactPhone: normalizeNigerianPhone(
        details.emergencyContactPhone
      ),
    });

    if (!result.success) {
      const fieldErrors: Record<string, string> = {};

      for (const issue of result.error.issues) {
        const field = String(issue.path[0]);
        if (!fieldErrors[field]) fieldErrors[field] = issue.message;
      }

      setErrors(fieldErrors);
      return false;
    }

    setDetails((current) => ({
      ...current,
      emergencyContactName: result.data.emergencyContactName,
      emergencyContactPhone: result.data.emergencyContactPhone,
    }));

    setErrors({});
    return true;
  }

  function handleContinue(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSuccessMessage("");

    if (step === 1) {
      if (!validatePersonalDetails()) return;
      setStep(2);
      return;
    }

    if (step === 2) {
      if (!validateCategory()) return;
      setStep(3);
      return;
    }

    if (step === 3) {
      if (!validateEmergencyContact()) return;
      setStep(4);
      return;
    }
  }

  function handleEditStep(nextStep: number) {
    setErrors({});
    setSuccessMessage("");
    setStep(nextStep);
  }

  function handleFinishReview() {
    // This is a local review checkpoint, not a completed registration.
    // The real OTP and registration API calls will be added when the
    // backend endpoints are available.
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(details));
    } catch {
      // Keep the review usable without storage.
    }

    setSuccessMessage(
      "Review complete. Your details are saved in this browser session. Registration has not been submitted yet."
    );
  }

  const inputClass =
    "w-full rounded-lg border border-gray-300 px-3 py-2.5 text-gray-900 outline-none focus:border-green-600 focus:ring-2 focus:ring-green-100";

  const selectedCategory = DEMO_CATEGORIES.find(
    (category) => category.id === details.categoryId
  );

  return (
    <main className="mx-auto max-w-3xl p-4 sm:p-6">
      <header className="mb-8">
        <p className="mb-2 text-sm font-semibold uppercase tracking-wider text-green-700">
          EkitiRun
        </p>
        <h1 className="text-3xl font-bold text-gray-900">
          Runner Registration
        </h1>
        <p className="mt-2 text-gray-600">
          Enter your details and review them before proceeding.
        </p>
      </header>

      <nav
        aria-label="Registration progress"
        className="mb-6 grid grid-cols-4 gap-2"
      >
        {["Personal", "Category", "Emergency", "Review"].map(
          (label, index) => {
            const number = index + 1;
            const active = step === number;
            const completed = step > number;

            return (
              <div
                key={label}
                className={`rounded-lg border p-2 text-center text-xs sm:text-sm ${
                  active
                    ? "border-green-700 bg-green-50 font-semibold text-green-800"
                    : completed
                      ? "border-green-200 bg-green-50 text-green-800"
                      : "border-gray-200 text-gray-500"
                }`}
                aria-current={active ? "step" : undefined}
              >
                <span className="block font-bold">{number}</span>
                {label}
              </div>
            );
          }
        )}
      </nav>

      <form
        noValidate
        onSubmit={handleContinue}
        className="space-y-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm sm:p-8"
      >
        {step === 1 && (
          <>
            <div>
              <h2 className="text-xl font-semibold text-gray-900">
                Personal Details
              </h2>
              <p className="mt-1 text-sm text-gray-500">
                Fields marked with * are required.
              </p>
            </div>

            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              <div>
                <label htmlFor="firstName" className="mb-1 block text-sm font-medium text-gray-700">
                  First name *
                </label>
                <input
                  id="firstName"
                  autoComplete="given-name"
                  value={details.firstName}
                  onChange={(e) => updateField("firstName", e.target.value)}
                  className={inputClass}
                  aria-invalid={Boolean(errors.firstName)}
                />
                {showError("firstName")}
              </div>

              <div>
                <label htmlFor="lastName" className="mb-1 block text-sm font-medium text-gray-700">
                  Last name *
                </label>
                <input
                  id="lastName"
                  autoComplete="family-name"
                  value={details.lastName}
                  onChange={(e) => updateField("lastName", e.target.value)}
                  className={inputClass}
                  aria-invalid={Boolean(errors.lastName)}
                />
                {showError("lastName")}
              </div>

              <div>
                <label htmlFor="gender" className="mb-1 block text-sm font-medium text-gray-700">
                  Gender *
                </label>
                <select
                  id="gender"
                  value={details.gender}
                  onChange={(e) => updateField("gender", e.target.value)}
                  className={`${inputClass} bg-white`}
                  aria-invalid={Boolean(errors.gender)}
                >
                  <option value="">Select gender</option>
                  <option value="M">Male</option>
                  <option value="F">Female</option>
                </select>
                {showError("gender")}
              </div>

              <div>
                <label htmlFor="dateOfBirth" className="mb-1 block text-sm font-medium text-gray-700">
                  Date of birth *
                </label>
                <input
                  id="dateOfBirth"
                  type="date"
                  autoComplete="bday"
                  max={new Date().toISOString().slice(0, 10)}
                  value={details.dateOfBirth}
                  onChange={(e) => updateField("dateOfBirth", e.target.value)}
                  className={inputClass}
                  aria-invalid={Boolean(errors.dateOfBirth)}
                />
                {showError("dateOfBirth")}
              </div>

              <div>
                <label htmlFor="email" className="mb-1 block text-sm font-medium text-gray-700">
                  Email address (optional)
                </label>
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  value={details.email}
                  onChange={(e) => updateField("email", e.target.value)}
                  className={inputClass}
                  placeholder="you@example.com"
                  aria-invalid={Boolean(errors.email)}
                />
                {showError("email")}
              </div>

              <div>
                <label htmlFor="phone" className="mb-1 block text-sm font-medium text-gray-700">
                  Nigerian phone number *
                </label>
                <input
                  id="phone"
                  type="tel"
                  autoComplete="tel"
                  value={details.phone}
                  onChange={(e) => updateField("phone", e.target.value)}
                  className={inputClass}
                  placeholder="08012345678 or +2348012345678"
                  aria-invalid={Boolean(errors.phone)}
                />
                {showError("phone")}
                <p className="mt-1 text-xs text-gray-500">
                  Local and international formats are accepted.
                </p>
              </div>
            </div>
          </>
        )}

        {step === 2 && (
          <section>
            <h2 className="text-xl font-semibold text-gray-900">
              Choose a Race Category
            </h2>
            <p className="mt-1 text-sm text-gray-600">
              Select the distance you want to run.
            </p>

            <div
              role="status"
              className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
            >
              {categoryNotice} These choices are for frontend testing only and
              must be replaced with the official categories before release.
            </div>

            <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
              {DEMO_CATEGORIES.map((category) => {
                const selected = details.categoryId === category.id;

                return (
                  <button
                    type="button"
                    key={category.id}
                    onClick={() => updateField("categoryId", category.id)}
                    aria-pressed={selected}
                    className={`rounded-xl border p-4 text-left transition ${
                      selected
                        ? "border-green-700 bg-green-50 ring-2 ring-green-100"
                        : "border-gray-200 hover:border-green-500"
                    }`}
                  >
                    <span className="block font-semibold text-gray-900">
                      {category.name}
                    </span>
                    <span className="mt-1 block text-sm text-gray-600">
                      {category.distance_km} km
                    </span>
                    <span className="mt-2 block text-xs text-gray-500">
                      {selected ? "Selected" : "Select this category"}
                    </span>
                  </button>
                );
              })}
            </div>
            {showError("categoryId")}
          </section>
        )}

        {step === 3 && (
          <section>
            <h2 className="text-xl font-semibold text-gray-900">
              Emergency Contact
            </h2>
            <p className="mt-1 text-sm text-gray-600">
              Provide someone the race organisers can contact in an emergency.
            </p>

            <div className="mt-5 space-y-5">
              <div>
                <label htmlFor="emergencyContactName" className="mb-1 block text-sm font-medium text-gray-700">
                  Contact person's full name *
                </label>
                <input
                  id="emergencyContactName"
                  autoComplete="name"
                  value={details.emergencyContactName}
                  onChange={(e) =>
                    updateField("emergencyContactName", e.target.value)
                  }
                  className={inputClass}
                  aria-invalid={Boolean(errors.emergencyContactName)}
                />
                {showError("emergencyContactName")}
              </div>

              <div>
                <label htmlFor="emergencyContactPhone" className="mb-1 block text-sm font-medium text-gray-700">
                  Contact person's Nigerian phone number *
                </label>
                <input
                  id="emergencyContactPhone"
                  type="tel"
                  autoComplete="tel"
                  value={details.emergencyContactPhone}
                  onChange={(e) =>
                    updateField("emergencyContactPhone", e.target.value)
                  }
                  className={inputClass}
                  placeholder="08012345678 or +2348012345678"
                  aria-invalid={Boolean(errors.emergencyContactPhone)}
                />
                {showError("emergencyContactPhone")}
              </div>
            </div>
          </section>
        )}

        {step === 4 && (
          <section>
            <h2 className="text-xl font-semibold text-gray-900">
              Review Your Registration
            </h2>
            <p className="mt-1 text-sm text-gray-600">
              Check your details carefully. Use Edit to make corrections.
            </p>

            <div className="mt-5 divide-y divide-gray-200 rounded-lg border border-gray-200">
              <div className="p-4">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="font-semibold text-gray-900">
                    Personal details
                  </h3>
                  <button
                    type="button"
                    onClick={() => handleEditStep(1)}
                    className="text-sm font-semibold text-green-700 hover:underline"
                  >
                    Edit
                  </button>
                </div>
                <dl className="mt-3 space-y-2 text-sm">
                  <div>
                    <dt className="text-gray-500">Full name</dt>
                    <dd className="font-medium text-gray-900">
                      {details.firstName} {details.lastName}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-gray-500">Gender</dt>
                    <dd className="text-gray-900">
                      {details.gender === "M" ? "Male" : "Female"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-gray-500">Date of birth</dt>
                    <dd className="text-gray-900">{details.dateOfBirth}</dd>
                  </div>
                  <div>
                    <dt className="text-gray-500">Email</dt>
                    <dd className="text-gray-900">
                      {details.email || "Not provided"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-gray-500">Phone</dt>
                    <dd className="text-gray-900">{details.phone}</dd>
                  </div>
                </dl>
              </div>

              <div className="p-4">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="font-semibold text-gray-900">Race category</h3>
                  <button
                    type="button"
                    onClick={() => handleEditStep(2)}
                    className="text-sm font-semibold text-green-700 hover:underline"
                  >
                    Edit
                  </button>
                </div>
                <p className="mt-2 text-sm text-gray-900">
                  {selectedCategory?.name} ({selectedCategory?.distance_km} km)
                </p>
                <p className="mt-1 text-xs text-amber-800">
                  Demo category only; not yet confirmed by the API.
                </p>
              </div>

              <div className="p-4">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="font-semibold text-gray-900">
                    Emergency contact
                  </h3>
                  <button
                    type="button"
                    onClick={() => handleEditStep(3)}
                    className="text-sm font-semibold text-green-700 hover:underline"
                  >
                    Edit
                  </button>
                </div>
                <p className="mt-2 text-sm text-gray-900">
                  {details.emergencyContactName}
                </p>
                <p className="text-sm text-gray-700">
                  {details.emergencyContactPhone}
                </p>
              </div>
            </div>

            <div className="mt-5 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
              This is a review checkpoint only. OTP verification and final
              registration submission will be connected when the backend
              endpoints are available.
            </div>
          </section>
        )}

        {successMessage && (
          <div
            role="status"
            className="rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-800"
          >
            {successMessage}
          </div>
        )}

        <div className="flex flex-col gap-3 border-t border-gray-200 pt-5 sm:flex-row sm:items-center sm:justify-between">
          {step > 1 ? (
            <button
              type="button"
              onClick={() => handleEditStep(step - 1)}
              className="rounded-lg border border-gray-300 px-5 py-3 font-semibold text-gray-700 hover:bg-gray-50"
            >
              Back
            </button>
          ) : (
            <span />
          )}

          {step < 4 ? (
            <button
              type="submit"
              className="w-full rounded-lg bg-green-700 px-5 py-3 font-semibold text-white transition hover:bg-green-800 sm:w-auto"
            >
              Continue
            </button>
          ) : (
            <button
              type="button"
              onClick={handleFinishReview}
              className="w-full rounded-lg bg-green-700 px-5 py-3 font-semibold text-white transition hover:bg-green-800 sm:w-auto"
            >
              Save Review
            </button>
          )}
        </div>
      </form>
    </main>
  );
}
