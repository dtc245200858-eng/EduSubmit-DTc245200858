using System.Net;
using System.Net.Http.Json;
var apiBaseUrl = args.Length > 0 ? args[0] : "http://localhost:5100";
using var http = new HttpClient {
BaseAddress = new Uri(apiBaseUrl)
};
// Bước 1: lấy danh sách sản phẩm
var products = await http.GetFromJsonAsync<List<ProductDto>>("/api/products");
Console.WriteLine("Danh sach san pham:");
foreach (var p in products ?? []) {
Console.WriteLine($"  [{p.Id}] {p.Name} -{p.Price:N0} VND");
}
var createRequest = new CreateProductRequest(
"Nhap mon REST API", "Sach tham khao", 120000);
var createResponse = await http.PostAsJsonAsync("/api/products", createRequest);
if (createResponse.StatusCode == HttpStatusCode.Created) {
var created = await createResponse.Content.ReadFromJsonAsync<ProductDto>();
Console.WriteLine($"\nDa tao san pham moi: [{created?.Id}] {created?.Name}");
Console.WriteLine($"Doc lai tai: {createResponse.Headers.Location}");
} else {
var error = await createResponse.Content.ReadFromJsonAsync<ApiError>();
Console.WriteLine($"\nLoi: {error?.Code} -{error?.Message}");
return;
}
// Bước 3: đọc lại chi tiết một sản phẩm
var detail = await http.GetFromJsonAsync<ProductDto>("/api/products/1");
Console.WriteLine($"\nChi tiet san pham 1: {detail?.Name}");
// Bước 4: Cố ý gửi dữ liệu sai để quan sát lỗi 400
var invalidResponse = await http.PostAsJsonAsync(
    "/api/products",
    new CreateProductRequest("", "", -1)
);

Console.WriteLine($"\nThu gui du lieu sai: {(int)invalidResponse.StatusCode} {invalidResponse.StatusCode}");

var invalidError = await invalidResponse.Content.ReadFromJsonAsync<ApiError>();

Console.WriteLine($"{invalidError?.Code}: {invalidError?.Message}");
// cuối tệp
record ProductDto(int Id, string Name, string Description, decimal Price);
record CreateProductRequest(string Name, string? Description, decimal Price);
record ApiError(string Code, string Message);