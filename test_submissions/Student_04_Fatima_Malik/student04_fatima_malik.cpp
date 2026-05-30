// Student: Fatima Malik | Level: PARTIAL (5/10)
// Logic is almost right but student hardcoded one value instead of taking input
// Shows understanding of addition concept but misses the input requirement

#include <iostream>
using namespace std;

int main() {
    int a;
    cout << "Enter a number: ";
    cin >> a;
    
    // Hardcoded second number — should have taken it from user
    int b = 10;
    
    cout << "Sum: " << a + b << endl;
    return 0;
}
