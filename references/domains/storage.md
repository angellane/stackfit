<!-- Loaded on demand for one domain. Shared guidance that applies to every
domain (existing-platform check, build vs buy) lives in SKILL.md. -->

# File storage and media

**Landscape.** Object stores (AWS S3, Cloudflare R2, Google Cloud Storage, Azure
Blob, Backblaze B2, MinIO self-hosted); developer-experience layers (UploadThing,
Vercel Blob, Supabase Storage); media-specialised (Cloudinary, imgix, Mux for
video).

**What usually decides it.**
- Are the files just stored, or transformed? Image resizing, format conversion and
  video transcoding are a different product category from object storage, and
  building them on raw S3 is a real project.
- Egress pricing, if files are read often. This is the classic surprise bill, and
  the reason S3-compatible alternatives with free egress win some decisions
  outright.
- Existing cloud provider - staying inside it saves credentials, egress and
  latency.
- Upload size and origin. Large files from the browser want direct-to-storage
  presigned uploads rather than proxying through the app server, and serverless
  request body limits often force this decision.

**Hidden requirements.** Presigned URL generation; file metadata records in your
own database (storage services are not a database); access control for private
files, including signed read URLs; virus scanning for user uploads in some
contexts; lifecycle/retention rules; orphan cleanup when a record is deleted but
the object isn't; CDN in front for read-heavy media.

**Portability is unusually good here.** The S3 API is a de facto standard, so
object storage is one of the few areas where a `portability` of 5 is defensible -
provided the code uses the standard API rather than provider-specific extensions.

**Verify.** Storage and egress rates, request pricing, transformation quotas,
maximum object size.
