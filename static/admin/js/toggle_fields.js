document.addEventListener("DOMContentLoaded", function () {
    const roleSelect = document.getElementById("id_role");
    if (!roleSelect) return;

    function toggleFields() {
        const isLecturer = roleSelect.value === "lecturer";
        
        // Find row fields by class name in Django Admin
        const indexRow = document.querySelector(".field-index_number");
        const groupRow = document.querySelector(".field-group");
        const devIdRow = document.querySelector(".field-device_id");
        const devNameRow = document.querySelector(".field-device_name");

        if (indexRow) indexRow.style.display = isLecturer ? "none" : "";
        if (groupRow) groupRow.style.display = isLecturer ? "none" : "";
        if (devIdRow) devIdRow.style.display = isLecturer ? "none" : "";
        if (devNameRow) devNameRow.style.display = isLecturer ? "none" : "";
    }

    toggleFields();
    roleSelect.addEventListener("change", toggleFields);
});
