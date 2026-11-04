
using System.Net.Http.Json;

var baseUrl = args.Length > 0
    ? args[0]
    : "http://localhost:5081";

using var httpClient = new HttpClient
{
    BaseAddress = new Uri(baseUrl)
};

try
{
    Console.WriteLine("==================================");
    Console.WriteLine("       EDUSUBMIT CLIENT");
    Console.WriteLine("==================================");

    // 1. Lay danh sach bai tap
    Console.WriteLine("\n1. DANH SACH BAI TAP");

    var assignments = await httpClient
        .GetFromJsonAsync<Assignment[]>("/api/assignments");

    if (assignments is null || assignments.Length == 0)
    {
        Console.WriteLine("Khong co bai tap nao.");
        return;
    }

    foreach (var assignment in assignments)
    {
        Console.WriteLine(
            $"{assignment.Id}. {assignment.Title} - {assignment.Description}");
    }

    // 2. Nhap thong tin bai nop
    Console.WriteLine("\n2. NHAP THONG TIN BAI NOP");

    Console.Write("Nhap ma bai tap (1 hoac 2): ");
    var assignmentInput = Console.ReadLine();

    if (!int.TryParse(assignmentInput, out var assignmentId))
    {
        Console.WriteLine("Ma bai tap phai la so.");
        return;
    }

    Console.Write("Nhap ma sinh vien: ");
    var studentCode = Console.ReadLine();

    Console.Write("Nhap URL GitHub cua bai lam: ");
    var repositoryUrl = Console.ReadLine();

    var request = new CreateSubmissionRequest(
        AssignmentId: assignmentId,
        StudentCode: studentCode ?? "",
        RepositoryUrl: repositoryUrl ?? ""
    );

    // 3. Gui bai nop len API
    Console.WriteLine("\n3. DANG GUI BAI NOP...");

    var response = await httpClient.PostAsJsonAsync(
        "/api/submissions",
        request
    );

    var responseBody = await response.Content.ReadAsStringAsync();

    Console.WriteLine($"HTTP Status: {(int)response.StatusCode}");
    Console.WriteLine($"Phan hoi: {responseBody}");

    if (!response.IsSuccessStatusCode)
    {
        Console.WriteLine("\nGui bai nop that bai.");
        return;
    }

    var result = await response.Content
        .ReadFromJsonAsync<SubmissionResult>();

    if (result is null)
    {
        Console.WriteLine("Khong doc duoc ket qua tra ve.");
        return;
    }

    Console.WriteLine("\nGUI BAI NOP THANH CONG!");
    Console.WriteLine($"Submission ID: {result.Id}");
    Console.WriteLine($"Trang thai: {result.Status}");

    // 4. Tra cuu lai bai nop
    Console.WriteLine("\n4. KIEM TRA BAI NOP");

    var savedSubmission = await httpClient
        .GetFromJsonAsync<SubmissionResult>(
            $"/api/submissions/{result.Id}"
        );

    if (savedSubmission is not null)
    {
        Console.WriteLine($"Ma sinh vien: {savedSubmission.StudentCode}");
        Console.WriteLine($"Ma bai tap: {savedSubmission.AssignmentId}");
        Console.WriteLine($"GitHub: {savedSubmission.RepositoryUrl}");
        Console.WriteLine($"Trang thai: {savedSubmission.Status}");
        Console.WriteLine($"Thoi gian nhan: {savedSubmission.ReceivedAt}");
    }
}
catch (HttpRequestException ex)
{
    Console.WriteLine($"Loi ket noi API: {ex.Message}");
    Console.WriteLine("Hay kiem tra API co dang chay khong.");
}
catch (Exception ex)
{
    Console.WriteLine($"Da xay ra loi: {ex.Message}");
}

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
