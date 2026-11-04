
var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();

// Danh sach bai tap
var assignments = new[]
{
    new Assignment(
        1,
        "Bai tap 1",
        "Tao API dau tien"
    ),
    new Assignment(
        2,
        "Bai tap 2",
        "Lam quen voi ung dung phan tan"
    )
};

// Luu bai nop trong bo nho khi API dang chay
var submissions = new Dictionary<Guid, SubmissionResult>();

// Trang chu kiem tra API
app.MapGet("/", () =>
{
    return Results.Ok(new
    {
        application = "EduSubmit",
        message = "Submission API is running."
    });
});

// Lay danh sach bai tap
app.MapGet("/api/assignments", () =>
{
    return Results.Ok(assignments);
});

// Gui bai nop
app.MapPost("/api/submissions", (CreateSubmissionRequest request) =>
{
    if (request.AssignmentId <= 0 ||
        !assignments.Any(a => a.Id == request.AssignmentId))
    {
        return Results.BadRequest(new
        {
            message = "AssignmentId khong hop le."
        });
    }

    if (string.IsNullOrWhiteSpace(request.StudentCode))
    {
        return Results.BadRequest(new
        {
            message = "StudentCode khong duoc de trong."
        });
    }

    if (string.IsNullOrWhiteSpace(request.RepositoryUrl))
    {
        return Results.BadRequest(new
        {
            message = "RepositoryUrl khong duoc de trong."
        });
    }

    var result = new SubmissionResult(
        Guid.NewGuid(),
        request.AssignmentId,
        request.StudentCode.Trim(),
        request.RepositoryUrl.Trim(),
        "received",
        DateTimeOffset.UtcNow
    );

    submissions[result.Id] = result;

    return Results.Created(
        $"/api/submissions/{result.Id}",
        result
    );
});

// Tra cuu bai nop theo ID
app.MapGet("/api/submissions/{id:guid}", (Guid id) =>
{
    if (!submissions.TryGetValue(id, out var submission))
    {
        return Results.NotFound(new
        {
            message = "Khong tim thay bai nop."
        });
    }

    return Results.Ok(submission);
});

// Xem tat ca bai nop
app.MapGet("/api/submissions", () =>
{
    return Results.Ok(submissions.Values);
});

app.Run();

// Cac model du lieu
record Assignment(
    int Id,
    string Title,
    string Description
);

record CreateSubmissionRequest(
    int AssignmentId,
    string StudentCode,
    string RepositoryUrl
);

record SubmissionResult(
    Guid Id,
    int AssignmentId,
    string StudentCode,
    string RepositoryUrl,
    string Status,
    DateTimeOffset ReceivedAt
);
